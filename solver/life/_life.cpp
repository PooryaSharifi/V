#include "osrm/match_parameters.hpp"
#include "osrm/nearest_parameters.hpp"
#include "osrm/route_parameters.hpp"
#include "osrm/table_parameters.hpp"
#include "osrm/trip_parameters.hpp"

#include "osrm/coordinate.hpp"
#include "osrm/engine_config.hpp"
#include "osrm/json_container.hpp"

#include "osrm/osrm.hpp"
#include "osrm/status.hpp"

#include "lap.h"

#include <exception>
#include <iostream>
#include <utility>
#include <cstdlib>
#include <chrono>
#include <unordered_map>
#include <tsl/robin_map.h>
#include <tsl/robin_set.h>
#include <vector>
#include <stack>
#include <queue>
#include <unistd.h>
#include <thread>
#include <cmath>
#include <cstddef>
#include <cerrno>
#include <sys/socket.h>
#include <sys/un.h>
#include <string>
#include <sstream>
#include <tuple>
#include <limits>
#include <curl/curl.h>
#include <algorithm>

using namespace osrm;
OSRM *osm;

typedef std::chrono::high_resolution_clock Clock;

#define MAX_N 2000
std::string hang;

/*  for each endpoint call on end if it was successful <<<<
for porter lock is the 10 sec push notification lock
for porter at is lock for delete preparation

for now no batching no familiarity no expected frees

>>> tonight batch, sell
*/

struct Std {
    std::string _id;
    float s[2];
    float t[2];
    float _t[2];
    int d;
    int eta;
    int prev;
    int idx;
    int next;
    int score;
    bool lock;
    bool at;
    bool cross;
    Std *baby;
};


typedef Std (*FnPtr)(std::string, float []);

tsl::robin_map<std::string, FnPtr> methods;
tsl::robin_map<std::string, Std> stds;
tsl::robin_map<std::string, int> id;
std::stack<int> bag;
std::vector<Std> line;  // by default line filled with free porters

int d [2 * MAX_N][2 * MAX_N];

bool update_lock;
Clock::time_point update_time_point = Clock::now();
tsl::robin_set<std::string> update_q;
int _map_to_d[MAX_N], _news_map_to_d[MAX_N];

void rnd(float* r, float* s, float* t) {
    r[0] = ((float) rand()) / (float) RAND_MAX;
    r[1] = ((float) rand()) / (float) RAND_MAX;
    r[0] = (t[0] - s[0]) * r[0] + s[0];
    r[1] = (t[1] - s[1]) * r[1] + s[1];
}

std::string string_join(const std::vector<std::string>& elements, const char* const separator)
{
    switch (elements.size())
    {
        case 0:
            return "";
        case 1:
            return elements[0];
        default:
            std::ostringstream os;
            std::copy(elements.begin(), elements.end() - 1, std::ostream_iterator<std::string>(os, separator));
            os << *elements.rbegin();
            return os.str();
    }
}

void push_loop() {
    // if before with now are equal don't notify
    // instantly push all instant batches < batch to locks >
    std::vector<std::string> data;
    while (true) {
        for (auto const& porter : line)
            if (porter.prev == -1 && porter.next != -1) {
                auto path = line[porter.next];
                std::string paths = porter._id + "," + path._id;
                bool flag = false;
                if (!path.lock) flag = true;
                if (path.baby) {
                    auto baby = *path.baby;
                    paths += "," + baby._id + (path.cross ? ",x" : ",z");
                    if (!baby.lock) flag = true;
                }
                if (flag)
                    data.push_back(paths);
            }

        CURL *curl;
        CURLcode res;

        static const char *postthis = ("matches=" + string_join(data, ";")).c_str();

        curl = curl_easy_init();
        if(curl) {
            curl_easy_setopt(curl, CURLOPT_URL, "http://localhost/" + hang + "/!!!/NN");
            curl_easy_setopt(curl, CURLOPT_POSTFIELDS, postthis);

            /* if we don't provide POSTFIELDSIZE, libcurl will strlen() by
               itself */
            curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, (long)strlen(postthis));

            /* Perform the request, res will get the return code */
            res = curl_easy_perform(curl);
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(1000));  // in 1sec segments
    }
}

void batch() {
    // you know if v matched u then u must match v -> sort with edge weight then iterate add u and v to set.
    std::vector <Std> paths;
    for (const auto &it : stds) {
        auto std = it.second;
        if (std::abs(std.s[0]) + std::abs(std.s[1]) > .1)
            paths.push_back(std);
    }

    auto n_dim = (int) paths.size();
    float cost [n_dim][n_dim];
    bool crosses [n_dim][n_dim];
    int rowsol[n_dim];
    int colsol[n_dim];
    float u[n_dim];
    float v[n_dim];
    bool flags[n_dim];
    for (int i = 0; i < n_dim; i ++) {
        u[i] = .0;
        v[i] = .0;
        flags[i] = true;
    }

    for (int i = 0; i < n_dim; i ++)
        for (int j = 0; j < n_dim; j ++) {
            auto v = paths[i], u = paths[j];
            auto v_id = id[v._id], u_id = id[u._id];
            auto strait = d[2 * v_id][2 * u_id] + d[2 * u_id][2 * u_id + 1] + d[2 * u_id + 1][2 * v_id + 1]; // without d
            auto cross = d[2 * v_id][2 * u_id] + d[2 * u_id][2 * v_id + 1] + d[2 * v_id + 1][2 * u_id + 1];

            // you can define a threshold for both of them else inf. (and have to, must)
            if (cross < strait) {
                cost[i][j] = cross;
                crosses[i][j] = true;
            } else {
                cost[i][j] = strait;
                crosses[i][j] = false;
            }
        }

    auto cost_matrix = reinterpret_cast<float*>(cost);
    lap(n_dim, cost_matrix, 0, rowsol, colsol, u, v);  // verbose = 0
    std::vector <std::tuple<int, int, int>> result;

    for (int i = 0; i < n_dim; i ++)
        result.push_back(std::make_tuple(u[i], i, rowsol[i]));
    sort(result.begin(), result.end());

    for (int i = 0; i < n_dim; i ++)
        if (std::get<0>(result[i]) < (int) std::numeric_limits<int>::max()) {
            auto v_idx = std::get<1>(result[i]), u_idx = std::get<2>(result[i]);
            if (flags[v_idx] && flags[u_idx]) {
                flags[v_idx] = false; flags[u_idx] = false;
                auto v = paths[v_idx], u = paths[u_idx];
                auto cross = crosses[v_idx][u_idx];

                v.baby = &u;
                v.cross = cross;
            }
        }
}

void match(int undo, int redo) {
    // TODO it is wrong reverse iterate through line if it was not lock and prev was not lock
    while (undo && line.size() && line.back()._id.length() == 24) {
        undo --;
        line.pop_back();
    }
    redo -= undo;
    // get heads from line .t
    tsl::robin_set<std::string> already, orphans;
    std::vector<Std> heads;
    int heads_size = 0;
    for (auto const &it : line) {
        if (it._id.length() == 24)
            already.insert(it._id);
        if (it.next == -1)
            heads.push_back(it);
            // heads_size ++;
    }
    for (auto const &it : stds)
        if (it.first.length() == 24 && already.find(it.first) != already.end())
            orphans.insert(it.first);
    Std orphans_array[orphans.size()];
    // int paths_size = stds.size() - line.size() + already.size();
    while (redo && already.size() < orphans.size()) {
        int n_dim = std::max(heads.size(), orphans.size());  // (heads_size, orphans.size());
        float cost [n_dim][n_dim];
        int rowsol[n_dim];
        int colsol[n_dim];
        float u[n_dim];
        float v[n_dim];
        for (int i = 0; i < n_dim; i ++) {
            u[i] = .0;
            v[i] = .0;
        }
        for (int i = 0; i < n_dim; i ++)
            for (int j = 0; j < n_dim; j ++)
                cost[i][j] = (int) std::numeric_limits<int>::max();
        // sort edges
        // while redo: add
        int i = 0;
        // TODO order of orphans is not granted
        for (auto const &head : heads) {
            int j = 0;
            for (auto const &orphan_name : orphans) {
                auto orphan = stds[orphan_name];
                auto delay = (orphan.d - head.eta);  // std::abs removed
                orphans_array[j] = orphan;
                cost[i][j ++] = std::max(delay, d[2 * id[head._id] + 1][2 * id[orphan_name]]);
            }
            i ++;
        }

        auto cost_matrix = reinterpret_cast<float*>(cost);
        lap(n_dim, cost_matrix, 0, rowsol, colsol, u, v);  // verbose = 0

        for (int i = 0; i < heads.size() && redo; i ++) {
            auto candidate = orphans_array[rowsol[i]];
            auto head = heads[i];
            candidate.idx = (int) line.size();
            candidate.prev = head.idx;
            head.next = candidate.idx;
            auto d_id = id[candidate._id];
            candidate.eta = cost[i][rowsol[i]] + d[2 * d_id][2 * d_id + 1];
            line.push_back(candidate);
            redo --;
        }

        // TODO so simple we just push all. with out sorting two problem one the line is not sorted for now
    }
}

void _update(int milliseconds) {
    if (update_lock) return;
    std::this_thread::sleep_for(std::chrono::milliseconds(milliseconds));
    update_lock = true;

    TableParameters forward, backward;

    int ptr = 0, news_ptr = 0;
    for (auto const& it : stds) {
        auto one_all = it.second;
        auto _id = it.first;
        std::cout << _id << std::endl;
        forward.coordinates.push_back({util::FloatLongitude{one_all.s[1]}, util::FloatLatitude{one_all.s[0]}});
        forward.coordinates.push_back({util::FloatLongitude{one_all.t[1]}, util::FloatLatitude{one_all.t[0]}});
        backward.coordinates.push_back({util::FloatLongitude{one_all.s[1]}, util::FloatLatitude{one_all.s[0]}});
        backward.coordinates.push_back({util::FloatLongitude{one_all.t[1]}, util::FloatLatitude{one_all.t[0]}});

        forward.destinations.push_back(2 * ptr);
        forward.destinations.push_back(2 * ptr + 1);
        backward.sources.push_back(2 * ptr);
        backward.sources.push_back(2 * ptr + 1);

        if (update_q.find(_id) != update_q.end()) {
            forward.sources.push_back(2 * ptr);
            forward.sources.push_back(2 * ptr + 1);
            backward.destinations.push_back(2 * ptr);
            backward.destinations.push_back(2 * ptr + 1);
            _news_map_to_d[news_ptr ++] = id[_id];
        }

        _map_to_d[ptr ++] = id[_id];
    }
    update_q.clear(); // If needed.

    json::Object forward_result, backward_result;
    const auto forward_status = osm -> Table(forward, forward_result);
    const auto backward_status = osm -> Table(backward, backward_result);

    auto &forward_durations = forward_result.values["durations"].get<json::Array>().values;
    auto &backward_durations = backward_result.values["durations"].get<json::Array>().values;

    // std::cout << durations.front().get<json::Array>().values.at(1).get<json::Number>().value << "\n";
    // update d for both forward and backward
    std::cout << forward_durations.size() << " " << backward_durations.size() << std::endl;
    for (int row = 0; row < news_ptr; row ++) {
        auto row_id = _news_map_to_d[row];
        auto even_row = forward_durations.at(2 * row).get<json::Array>().values;
        auto odd_row = forward_durations.at(2 * row + 1).get<json::Array>().values;
        for (int col = 0; col < ptr; col ++) {
            auto col_id = _map_to_d[col];
            d[2 * row_id][2 * col_id] = even_row.at(2 * col).get<json::Number>().value;
            d[2 * row_id][2 * col_id + 1] = even_row.at(2 * col + 1).get<json::Number>().value;
            d[2 * row_id + 1][2 * col_id] = odd_row.at(2 * col).get<json::Number>().value;
            d[2 * row_id + 1][2 * col_id + 1] = odd_row.at(2 * col + 1).get<json::Number>().value;
        }
    }

    for (int row = 0; row < ptr; row ++) {
        auto row_id = _map_to_d[row];
        auto even_row = backward_durations.at(2 * row).get<json::Array>().values;
        auto odd_row = backward_durations.at(2 * row + 1).get<json::Array>().values;
        for (int col = 0; col < news_ptr; col ++) {
            auto col_id = _news_map_to_d[col];
            d[2 * row_id][2 * col_id] = even_row.at(2 * col).get<json::Number>().value;
            d[2 * row_id][2 * col_id + 1] = even_row.at(2 * col + 1).get<json::Number>().value;
            d[2 * row_id + 1][2 * col_id] = odd_row.at(2 * col).get<json::Number>().value;
            d[2 * row_id + 1][2 * col_id + 1] = odd_row.at(2 * col + 1).get<json::Number>().value;
        }
    }
    update_time_point = Clock::now();
    update_lock = false;

    std::thread(match, stds.size(), stds.size()).detach();
}

void update_d(Std std) {
    update_q.insert(std._id);
    int delay = 1000 * 6 * exp(-7 / 10 * sqrt(update_q.size())) + 333;
    Clock::time_point now = Clock::now();
    Clock::time_point _update_time_point = now + std::chrono::milliseconds(delay);
    if (update_time_point < now || _update_time_point < update_time_point) {
        update_time_point = _update_time_point;
        std::thread t = std::thread(_update, delay);
        t.detach();
    }
}

Std remove(std::string _id, float args[]) {
    // if not in path delete else flag
    // in done if flag delete
    Std std;
    if (stds.find(_id) == stds.end())
        return std;

//    std = stds[_id];
//    std.t[0] = lat; std.t[1] = lng;
//    std.d = d;
    return std;
}

Std location(std::string _id, float args[]) {  // d = now
    auto lat = args[0], lng = args[1];
    int d = args[2];
    Std std;
    if (stds.find(_id) != stds.end()) {
        std = stds[_id];
        std.t[0] = lat; std.t[1] = lng;
        std.d = d;
    } else {
        std = { _id, {0, 0}, {lat, lng}, {0, 0}, d, 0, -1, (int) line.size(), -1, -1, false, false, false, nullptr };
        stds[std._id] = std;
        id[std._id] = bag.top(); bag.pop();
        line.insert(line.begin(), std);
    }
    if (abs(std.t[0] - std._t[0]) + abs(std.t[1] - std._t[1]) > .000001 && std.next == -1) {
        std._t[0] = std.t[0];
        std._t[1] = std.t[1];
        update_d(std);
    }

    return std;
}

Std insert(std::string _id, float args[]) {
    auto slat = args[0], slng = args[1];
    auto tlat = args[2], tlng = args[3];
    int d = args[4];
    Std std = { _id, {slat, slng}, {tlat, tlng}, {0, 0}, d, 0, -1, -1, -1, -1, false, false, false, nullptr };
    stds[std._id] = std;
    id[std._id] = bag.top(); bag.pop();
    update_d(std);
    return std;
}

Std sell(std::string _id, std::string args[]) {  // no need for anything with topology we can find if it is batch and who is, KHAFE baba
    auto std = stds[_id];
    std.lock = true;
    return std;

    // if its prev and baby was not true -> add to q of match() -> match it self reposition them -> rematch all in a thread
}

Std at(std::string _id, float args[]) {
    auto std = stds[_id];
    std.at = true;
    return std;
}

Std done(std::string _id, float args[]) {
    bag.push(id[_id]);
    id.erase(_id);
    Std std = stds[_id];
    stds.erase(_id);

    // undo all changes from previous steps
    // in line
    // it has next, prev(porter) must join them
    // if hase baby dont join between them it's baby

    // copy ds of loc with it's
    Std p = line[std.prev];
    int pid = id[p._id] * 2 + 1, tid = id[std._id] * 2 + 1;
    for (auto& it: id) {
        d[pid][it.second * 2] = d[tid][it.second * 2];
        d[pid][it.second * 2 + 1] = d[tid][it.second * 2 + 1];
        d[it.second * 2][pid] = d[it.second * 2][tid];
        d[it.second * 2 + 1][pid] = d[it.second * 2 + 1][tid];
    }
    /*
    for(auto it = map.begin(); it != map.end(); ++it) {
        //it->second = 2; // Illegal
        it.value() = 2; // Ok
    }
    */
    return std;
}

int test() {
    /*
    match -> sort -> choose -> match*
        -> cost -> lap ->
    d changes -> undo(t) -> redo upper loop
    list have to update d[][] -> new path, free's location
    #2 on at and sell we can update eta
    open file containing mus then create cost <
    */

//    int now = duration_cast< milliseconds >(
//        system_clock::now().time_since_epoch()
//    ).count() / 1000;

    auto _now = std::chrono::system_clock::now();
    int now = std::chrono::system_clock::to_time_t( _now );

//    Std _0 = location ("mohammad", (float[]){35.753595, 51.295330, (float) now});
//    Std _1 = location ("ali", {35.756247, 51.465695, now});
//    Std _2 = location ("ahmad", {35.655340, 51.382212, now});


    Std _0;
    Std _1;
    Std _2;
    // init some points suppose std
    Std p0 = {
        ._id = "0",
    };
    p0.s[0] = 35.751020;
    p0.s[1] = 51.348189;
    p0.d = now + 2;
    stds[p0._id] = p0;
    id[p0._id] = bag.top(); bag.pop();
    line.push_back(p0);

    Std p1 = {
        ._id = "1",
    };
    p1.s[0] = 35.749913;
    p1.s[1] = 51.420229;
    p1.d = now + 5;
    stds[p1._id] = p1;
    id[p1._id] = bag.top(); bag.pop();
    line.push_back(p1);

    d[id[_0._id] * 2 + 1][id[p0._id] * 2] = abs(_0.t[0] - p0.s[0]) + abs(_0.t[1] - p0.s[1]);
    d[id[_0._id] * 2 + 1][id[p1._id] * 2] = abs(_0.t[0] - p1.s[0]) + abs(_0.t[1] - p1.s[1]);
    d[id[_1._id] * 2 + 1][id[p0._id] * 2] = abs(_1.t[0] - p0.s[0]) + abs(_1.t[1] - p0.s[1]);
    d[id[_1._id] * 2 + 1][id[p1._id] * 2] = abs(_1.t[0] - p1.s[0]) + abs(_1.t[1] - p1.s[1]);
    d[id[_2._id] * 2 + 1][id[p0._id] * 2] = abs(_2.t[0] - p0.s[0]) + abs(_2.t[1] - p0.s[1]);
    d[id[_2._id] * 2 + 1][id[p1._id] * 2] = abs(_2.t[0] - p1.s[0]) + abs(_2.t[1] - p1.s[1]);

    auto _end = std::chrono::system_clock::now();
    int end = std::chrono::system_clock::to_time_t( _end );
    std::cout << '\n' << end - now << '\n';
//    std::cout << rowsol[0] << ' ' << rowsol[1] << ' ' << rowsol[2] << '\n';
//    std::cout << colsol[0] << ' ' << colsol[1] << ' ' << colsol[2] << '\n';
//
//    std::cout << u[0] << ' ' << u[1] << ' ' << u[2] << '\n';
//    std::cout << v[0] << ' ' << v[1] << ' ' << v[2] << '\n';

    return EXIT_SUCCESS;
}


int main(int argc, const char *argv[]) {
    for (int i = 0; i < MAX_N; i++)
        bag.push(i);
    methods["location"] = location;
    methods["insert"] = insert;
    methods["remove"] = remove;
    methods["at"] = at;
    methods["done"] = done;

    EngineConfig config;
    config.storage_config = {argv[2]};
    config.use_shared_memory = false;
    config.algorithm = EngineConfig::Algorithm::CH;
    OSRM _osrm = OSRM(config);
    osm = &_osrm;

    hang = argv[1];
    const char *NAME = (std::string("/tmp/") + argv[1] + ".s").c_str();
    int sock, length;
    struct sockaddr_un name;
    char buff[1024];

    /* Create socket from which to read. */
    sock = socket(AF_UNIX, SOCK_DGRAM, 0);
    if (sock < 0) {
        perror("opening datagram socket");
        exit(1);
    }

    name.sun_family = AF_UNIX;
    strcpy(name.sun_path, NAME);

    std::remove(NAME);
    if (bind(sock, (struct sockaddr *) &name, sizeof(struct sockaddr_un))) {
        perror("binding name to datagram socket");
        exit(1);
    }

    std::string token = "";
    std::string method = "", _id = "";
    int buff_p, buff_size, args_p = 0;
    float args[] = {0, 0, 0, 0, 0, 0, 0};
    std::string sell_args[7];
    while (true) {
        buff_size = recv(sock, buff, 1024, 0);
        for (buff_p = 0; buff_p < buff_size; buff_p ++) {
            if (buff[buff_p] == ',') {
                if (method == "") method = token;
                else if (_id == "") _id = token;
                else if (method == "sell") sell_args[args_p ++] = token;
                else args[args_p ++] = std::stof(token);
                token = "";
                continue;
            }
            token += buff[buff_p];
        }
        if (method == "sell") sell(_id, sell_args);
        else methods[method](_id, args);
        args_p = 0;
        token = "";
        method = "";
        _id = "";
    }
    close(sock);
    unlink(NAME);

    return EXIT_SUCCESS;
}