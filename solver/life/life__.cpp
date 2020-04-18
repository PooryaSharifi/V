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
#include <sys/resource.h>
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
#include <deque>
#include <set>
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
#include <mutex>
#include <curl/curl.h>
#include <random>
#include <algorithm>

using namespace osrm;
OSRM *osm;

typedef std::chrono::high_resolution_clock Clock;

#define MAX_N 2000 * 3
std::string hang;

/*
for now no familiarity no expected frees
*/

struct Std {
    std::string _id;
    std::string porter;
    float s[2];
    float t[2];
    float _t[2];
    int d;
    int eta;
    int score;
    bool lock;
    bool cross;
    Std *baby;
};

struct ptr_comparision {
    bool operator()(const Std* lhs, const Std* rhs) const { return lhs -> porter == rhs -> porter ? lhs -> eta < rhs -> eta : lhs -> porter < rhs -> porter; }
};

typedef Std* (*FnPtr)(std::string, float []);

tsl::robin_map<std::string, FnPtr> methods;
tsl::robin_map<std::string, Std*> stds;
std::set<Std*, ptr_comparision> line;
tsl::robin_map<std::string, int> id;
std::stack<int> bag;
int d [2 * MAX_N][2 * MAX_N];
std::mutex osm_let, match_let;

tsl::robin_map<std::string, Std*> *stds_q = new tsl::robin_map<std::string, Std*>();
TableParameters *forward = new TableParameters(), *backward = new TableParameters();
std::vector<int> *map_to_d = new std::vector<int>();

tsl::robin_map<std::string, tsl::robin_set<std::string>*> checklist;

bool by_third(const std::tuple<float, int, int>& a, const std::tuple<float, int, int>& b) {
    return (std::get<2>(a) < std::get<2>(b));
}

bool reversed_by_second(const std::tuple<float, int, int>& a, const std::tuple<float, int, int>& b) {
    return (std::get<1>(a) > std::get<1>(b));
}

std::string string_join(const std::vector<std::string>& elements, const char* const separator) {
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

void show_me() {
    bool saw = false;
    for (auto const &p : line) {
        if (p -> s[0] + p -> s[1] < .01) {
            saw = true;
            std::cout << (p -> lock ? "\n@ " : "\n* ");
        } else {
            if (!saw && p -> lock) {
                std::cout << "haa ha ha " << p -> _id << " " << p -> porter << " " << p -> eta << std::endl;
                throw;
            }
            saw = false;
            std::cout << (p -> lock ? ">" : "");
        }
        std::cout << p -> _id;
        if (p -> baby)
            std::cout << " ^ " << p -> baby -> _id << " - ";
        else
            std::cout << " - ";
    }
    std::cout << std::endl;
}

void check(std::string action) {
    bool saw = false;
    std::string porter = "_";
    for (auto const &p : line) {
        if (p -> s[0] + p -> s[1] < .01) {
            porter = p -> _id;
            saw = true;
        } else {
            if (!saw && p -> lock) {
                std::cout << "> " << action << " somebody is lock " << std::endl;
                show_me();
                throw;
            }
            if (p -> porter != porter) {
                std::cout << "> " << action << " porter miss match " << std::endl;
                show_me();
                throw;
            }
            saw = false;
        }
    }
}

void push() {
    std::vector<std::string> data;
    Std *porter;
    match_let.lock();
    for (auto const& std : line) {
        if (std -> s[0] + std -> s[1] > .01) {
            auto path = std;
            if (porter) {
                std::string paths = porter -> _id + "," + path -> _id;
                bool flag = false;
                if (!(path -> lock)) flag = true;
                if (path -> baby) {
                    auto baby = path -> baby;
                    paths += "," + baby -> _id + (path -> cross ? ",x" : ",z");
                    if (checklist.find(path -> _id) == checklist.end())
                        checklist[path -> _id] = new tsl::robin_set<std::string> ();
                    auto list = checklist[path -> _id];
                    if (checklist.find(baby -> _id) == checklist.end())
                        checklist[baby -> _id] = new tsl::robin_set<std::string> ();
                    auto baby_list = checklist[path -> _id];
                    std::string path_key, baby_key;
                    if (path -> lock && !(baby -> lock)) {
                        path_key = porter -> _id + "," + baby -> _id + "," + "01";
                        baby_key = porter -> _id + "," + path -> _id + "," + "11";
                        flag = true;
                    } else {
                        path_key = porter -> _id + "," + baby -> _id + "," + "00";
                        baby_key = porter -> _id + "," + path -> _id + "," + "10";
                    }
                    if (list -> find(path_key) != list -> end())
                        ; //flag = false;
                    else
                        list -> insert(path_key);
                    if (baby_list -> find(baby_key) != baby_list -> end())
                        ; //flag = false;
                    else
                        baby_list -> insert(baby_key);
                } else {
                    if (checklist.find(path -> _id) == checklist.end())
                        checklist[path -> _id] = new tsl::robin_set<std::string> ();
                    auto list = checklist[path -> _id];
                    if (list -> find(porter -> _id) != list -> end())
                        ; //flag = false;
                    else
                        list -> insert(porter -> _id);
                }
                if (flag)
                    data.push_back(paths);
            }
            porter = nullptr;
        } else
            porter = std;
    }
    match_let.unlock();

    auto post_data = string_join(data, ";");
    if (post_data.length() != 0) {
        CURL *curl;
        CURLcode res;
        data.clear();
        curl = curl_easy_init();
        if(curl) {
            curl_easy_setopt(curl, CURLOPT_URL, ("http://localhost/v0.2/" + hang + "/!!!/NN").c_str());
            curl_easy_setopt(curl, CURLOPT_POSTFIELDS, post_data.c_str());
            curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, post_data.length());
            res = curl_easy_perform(curl);
            curl_easy_cleanup(curl);
        }
    }
}

void push_loop() {
    while (true) {
        push();
        std::this_thread::sleep_for(std::chrono::milliseconds(1000));  // in 1sec segments
    }
}

void batch(std::set<Std*, ptr_comparision> &orphans, std::vector<Std*> heads) {
    match_let.unlock();
    tsl::robin_set<std::string> parents, babies;
    std::vector<Std*> halves, randoms, shuffled, flatten;
    match_let.lock();
    for (auto const &orphan : orphans) {
        if (orphan -> baby) {
            auto baby = orphan -> baby;
//            baby -> porter = "_";  // here is it nessessary
            baby -> eta = orphans.size() + flatten.size();
            flatten.push_back(baby);
//            orphans.insert(baby);
            baby -> baby = nullptr;
            orphan -> baby = nullptr;
        }
        halves.push_back(orphan);
        randoms.push_back(orphan);
        shuffled.push_back(orphan);
    }
    while (!flatten.empty()) {
        orphans.insert(flatten.back());
        flatten.pop_back();
    }
//    for (auto const &head : heads)
//        if (head -> s[0] + head -> s[1] > .01)
//            halves.push_back(head);
//    auto rng = std::default_random_engine {};
//    std::shuffle(shuffled.begin(), shuffled.end(), rng);
//    for (int i = 0; i < halves.size() - shuffled.size(); i ++)
//        randoms.push_back(shuffled[i]);
    match_let.unlock();
    auto n_dim = halves.size();
    float cost [n_dim][n_dim];
    bool crosses [n_dim][n_dim];
    int rowsol[n_dim];
    int colsol[n_dim];
    float u[n_dim];
    float v[n_dim];
    for (int i = 0; i < n_dim; i ++) {
        u[i] = .0;
        v[i] = .0;
        parents.insert(halves[i] -> _id);
        if (i < orphans.size())
            babies.insert(randoms[i] -> _id);
    }
    osm_let.lock();
    for (int i = 0; i < n_dim; i ++) {
        auto vp = halves[i];
        for (int j = 0; j < n_dim; j ++) {
            auto up = randoms[j];
            try {
                if (id.find(up -> _id) == id.end())
                    std::cout << up -> _id << " * " << std::endl;
            } catch (int e) {
                std::cout << up -> _id << " ** " << std::endl;
                throw;
            }
            auto v_id = id[vp -> _id], u_id = id[up -> _id];
            auto delay = up -> d - vp -> d;
            delay = std::max(delay, d[2 * v_id][2 * u_id]);
            auto straight = delay + d[2 * u_id][2 * u_id + 1] + d[2 * u_id + 1][2 * v_id + 1];
            auto cross = delay + d[2 * u_id][2 * v_id + 1] + d[2 * v_id + 1][2 * u_id + 1];
            // you can define a threshold for both of them else inf. (and have to, must)
            if (vp -> _id == up -> _id || up -> lock || std::min(straight, cross) > (d[2 * v_id][2 * v_id + 1] + d[2 * u_id][2 * u_id + 1]) * 5 / 4 + std::max(0, up -> d - vp -> d) / 4)
                cost[i][j] = (int) std::numeric_limits<int>::max();
            else if (cross < straight) {
                cost[i][j] = cross;
                crosses[i][j] = true;
            } else {
                cost[i][j] = straight;
                crosses[i][j] = false;
            }
        }
    }
    osm_let.unlock();
    auto cost_matrix = reinterpret_cast<float*>(cost);
    lap(n_dim, cost_matrix, 0, rowsol, colsol, u, v);  // verbose = 0
    std::vector <std::tuple<float, int, int>> result;

    for (int i = 0; i < n_dim; i ++)
        result.push_back(std::make_tuple(cost[i][rowsol[i]], i, rowsol[i]));
    sort(result.begin(), result.end());
    while (!result.empty() && std::get<0>(result.back()) > (int) std::numeric_limits<int>::max() / 2) result.pop_back();
    sort(result.begin(), result.end(), reversed_by_second);
    match_let.lock();
    // batch them if !lock
    for (auto it = orphans.begin(); it != orphans.end(); ) {
        if ((*it) -> lock)
            it = orphans.erase(it);
        else
            ++ it;
    }
    for (int i = 0; i < result.size(); i ++) {
        auto v_idx = std::get<1>(result[i]), u_idx = std::get<2>(result[i]);
        auto vp = halves[v_idx], up = randoms[u_idx];
        if (!vp -> baby && !up -> baby && !up -> lock && parents.find(vp -> _id) != parents.end() && babies.find(up -> _id) != babies.end() && orphans.find(up) != orphans.end()) {
            parents.erase(vp -> _id);
            parents.erase(up -> _id);
            babies.erase(vp -> _id);
            babies.erase(up -> _id);

            auto cross = crosses[v_idx][u_idx];
            vp -> baby = up;
            up -> baby = vp;
            vp -> cross = cross;
            up -> cross = false;
            int deleted = orphans.erase(up);
            if (!deleted) {  // yeki ye jaye dige avazesh mikone dige
                std::cout << "my my my\n" << up -> _id << " " << up -> porter << " " << up -> eta << std::endl;
                for (auto const &p : orphans)
                    std::cout << p -> _id << ",, " << p -> porter << ", " << p -> eta << ". ";
                std::cout << std::endl;
                throw;
            }
        }
    }
    check("batch");
    match_let.unlock();
}

//bool hope;
void match() {
    // but for locks one just one thread has permission
//    std::cout << "matching ..." << std::endl;  // <<<<
    std::set<Std*, ptr_comparision> orphans;
    std::vector<Std*> heads;
    match_let.lock();
    for (auto const &it : stds) {  // add news
        auto p = it.second;
        if (p -> s[0] + p -> s[1] > .01 && !p -> lock && line.find(p) == line.end() && (!p -> baby || line.find(p -> baby) == line.end())) {
            p -> eta = orphans.size();
            orphans.insert(p);
        }
    }
    for (auto it = line.begin(); it != line.end(); ) {  // add alreadies
        auto p = *it;
        if (p -> s[0] + p -> s[1] > .01 && !p -> lock) {
            p -> eta = orphans.size();
            p -> porter = "_";
            orphans.insert(p);
            it = line.erase(it);
        } else {  // last night heads.back while was empty <- maybe now fixed let's try
            if (p -> s[0] + p -> s[1] < .01)
                heads.push_back(p);
            heads.back() = p;
            ++it;
        }
    }
    match_let.unlock();
    batch(orphans, heads);
    // hope = true;
    // if (heads.empty() || orphans.empty()) hope = false;
    while (!heads.empty() && !orphans.empty()  /* && hope */) {
//        hope = false;
        int n_dim = std::max(heads.size(), orphans.size());
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

        int i = 0, j = 0;
        osm_let.lock();
        for (auto const &head : heads) {
            for (auto const &orphan : orphans) {
                auto delay = head -> eta;
                if (head -> baby && head -> cross) delay = head -> baby -> eta;
                delay = std::abs(orphan -> d - delay);
                cost[i][j ++] = std::max(delay, d[2 * id[head -> _id] + 1][2 * id[orphan -> _id]]);
            }
            i ++; j = 0;
        }
        osm_let.unlock();

        auto cost_matrix = reinterpret_cast<float*>(cost);
        lap(n_dim, cost_matrix, 0, rowsol, colsol, u, v);  // verbose = 0

        std::vector <std::tuple<float, int, int>> result;
        for (int i = 0; i < heads.size(); i ++)
            result.push_back(std::make_tuple(cost[i][rowsol[i]], i, rowsol[i]));
        sort(result.begin(), result.end());
        while (std::get<0>(result.back()) > (int) std::numeric_limits<int>::max() / 2) result.pop_back();

        sort(result.begin(), result.end(), by_third);
        i = 0;
        int ptr = 0;
        match_let.lock();
        for (auto it = orphans.begin(); it != orphans.end() && ptr < result.size(); ) {
            if (std::get<2>(result[ptr]) == i) {
                auto head = heads[std::get<1>(result[ptr])];
                auto head_it = line.find(head);
                auto candidate = *it;
                // age porter pas hast -> nextesh age ba candidate yeki nabud no insert va bayad head avaz beshe.
                if (head -> s[0] + head -> s[1] > .01 && head_it == line.end()) {
                    head -> eta = 0;
                    auto front = line.lower_bound(head);
                    if (++front != line.end() && (*front) -> s[0] + (*front) -> s[1] > .01)
                        heads[std::get<1>(result[ptr])] = *front;
                    else
                        heads[std::get<1>(result[ptr])] = *--front;
                } else if(head -> s[0] + head -> s[1] < .01 && ++head_it != line.end() && (*head_it) -> s[0] + (*head_it) -> s[1] > .01 && (*head_it) -> _id != candidate -> _id) {
                    heads[std::get<1>(result[ptr])] = *++line.find(head);
                } else {
                    it = orphans.erase(it);
                    auto d_id = id[candidate -> _id];
                    candidate -> eta = head -> eta + cost[std::get<1>(result[ptr])][std::get<2>(result[ptr])] + d[2 * d_id][2 * d_id + 1];  // todo sorry it is wrong when baby.
                    candidate -> porter = head -> porter;
                    line.insert(candidate);
                    heads[std::get<1>(result[ptr])] = candidate;
//                    hope = true;
                }
                ptr ++;
            } else
                ++ it;
            i ++;
        }
        check("match");
        match_let.unlock();
    }
//    std::cout << "done matches." << std::endl;  // <<<<
}

void matching_loop() {
    while (true) {  // (!hope) {
        match();
        std::this_thread::sleep_for(std::chrono::milliseconds(3000));
    }
}

void osm_loop() {
    while (true) {
        if (!stds_q -> empty()) {
            std::cout << "running osm ..." << std::endl;  // <<<<
            tsl::robin_map<std::string, Std*> *_stds_q = stds_q;
            TableParameters *_forward = forward, *_backward = backward;
            std::vector<int> *_map_to_d = map_to_d;

            osm_let.lock();
            stds_q = new tsl::robin_map<std::string, Std*>();
            forward = new TableParameters();
            backward = new TableParameters();
            map_to_d = new std::vector<int>();
            osm_let.unlock();

            int news_ptr = _map_to_d -> size();
            for (auto const& it : stds) {
                if (_stds_q -> find(it.first) == _stds_q -> end()) {
                    auto one_all = it.second;
                    auto _id = it.first;
                    _forward -> coordinates.push_back({util::FloatLongitude{one_all -> s[1]}, util::FloatLatitude{one_all -> s[0]}});
                    _forward -> coordinates.push_back({util::FloatLongitude{one_all -> t[1]}, util::FloatLatitude{one_all -> t[0]}});
                    _backward -> coordinates.push_back({util::FloatLongitude{one_all -> s[1]}, util::FloatLatitude{one_all -> s[0]}});
                    _backward -> coordinates.push_back({util::FloatLongitude{one_all -> t[1]}, util::FloatLatitude{one_all -> t[0]}});

                    auto ptr = _map_to_d -> size();
                    _forward -> destinations.push_back(2 * ptr);
                    _forward -> destinations.push_back(2 * ptr + 1);
                    _backward -> sources.push_back(2 * ptr);
                    _backward -> sources.push_back(2 * ptr + 1);
                    _map_to_d -> push_back(id[_id]);
                }
            }

            json::Object forward_result, backward_result;
            const auto forward_status = osm -> Table(*_forward, forward_result);
            const auto backward_status = osm -> Table(*_backward, backward_result);

            auto &forward_durations = forward_result.values["durations"].get<json::Array>().values;
            auto &backward_durations = backward_result.values["durations"].get<json::Array>().values;

            for (int row = 0; row < news_ptr; row ++) {
                auto row_id = _map_to_d -> at(row);
                auto even_row = forward_durations.at(2 * row).get<json::Array>().values;
                auto odd_row = forward_durations.at(2 * row + 1).get<json::Array>().values;
                for (int col = 0; col < _map_to_d -> size(); col ++) {
                    auto col_id = _map_to_d -> at(col);
                    d[2 * row_id][2 * col_id] = even_row.at(2 * col).get<json::Number>().value;
                    d[2 * row_id][2 * col_id + 1] = even_row.at(2 * col + 1).get<json::Number>().value;
                    d[2 * row_id + 1][2 * col_id] = odd_row.at(2 * col).get<json::Number>().value;
                    d[2 * row_id + 1][2 * col_id + 1] = odd_row.at(2 * col + 1).get<json::Number>().value;
                }
            }

            for (int row = 0; row < _map_to_d -> size(); row ++) {
                auto row_id = _map_to_d -> at(row);
                auto even_row = backward_durations.at(2 * row).get<json::Array>().values;
                auto odd_row = backward_durations.at(2 * row + 1).get<json::Array>().values;
                for (int col = 0; col < news_ptr; col ++) {
                    auto col_id = _map_to_d -> at(col);
                    d[2 * row_id][2 * col_id] = even_row.at(2 * col).get<json::Number>().value;
                    d[2 * row_id][2 * col_id + 1] = even_row.at(2 * col + 1).get<json::Number>().value;
                    d[2 * row_id + 1][2 * col_id] = odd_row.at(2 * col).get<json::Number>().value;
                    d[2 * row_id + 1][2 * col_id + 1] = odd_row.at(2 * col + 1).get<json::Number>().value;
                }
            }

            for (auto const& it : *_stds_q) stds[it.first] = it.second;
            delete _stds_q;
            delete _forward;
            delete _backward;
            delete _map_to_d;
            std::cout << "osm done." << std::endl;  // <<<<
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(1600));
    }
}

void append(Std *one_all) {
    osm_let.lock();
    stds_q -> operator[](one_all -> _id) = one_all;
    forward -> coordinates.push_back({util::FloatLongitude{one_all -> s[1]}, util::FloatLatitude{one_all -> s[0]}});
    forward -> coordinates.push_back({util::FloatLongitude{one_all -> t[1]}, util::FloatLatitude{one_all -> t[0]}});
    backward -> coordinates.push_back({util::FloatLongitude{one_all -> s[1]}, util::FloatLatitude{one_all -> s[0]}});
    backward -> coordinates.push_back({util::FloatLongitude{one_all -> t[1]}, util::FloatLatitude{one_all -> t[0]}});

    auto ptr = map_to_d -> size();
    forward -> destinations.push_back(2 * ptr);
    forward -> destinations.push_back(2 * ptr + 1);
    backward -> sources.push_back(2 * ptr);
    backward -> sources.push_back(2 * ptr + 1);

    forward -> sources.push_back(2 * ptr);
    forward -> sources.push_back(2 * ptr + 1);
    backward -> destinations.push_back(2 * ptr);
    backward -> destinations.push_back(2 * ptr + 1);
    map_to_d -> push_back(id[one_all -> _id]);
    osm_let.unlock();
}
// tasmime man ine ke in mostaqiman dota chiz dashte bashe yekish stds_q va do oon vector ha

Std* remove(std::string _id, float args[]) {
    // if not in path delete else flag
    // in done if flag delete
    Std* p;
    if (stds.find(_id) == stds.end())
        return p;

//    std = stds[_id];
//    std.t[0] = lat; std.t[1] = lng;
//    std.d = d;
    return p;
}

Std* location(std::string _id, float args[]) {  // d = now
    auto lat = args[0], lng = args[1];
    int d = args[2];
    Std* p;
    if (stds.find(_id) != stds.end()) {
        p = stds[_id];
        p -> t[0] = lat; p -> t[1] = lng;
        p -> d = d;
        match_let.lock();
        auto p_it = line.find(p);
        if (p_it != line.end())
            line.erase(p_it);
        p -> eta = d;
        line.insert(p);
    } else {
        p = new Std{ _id, _id, {0, 0}, {lat, lng}, {0, 0}, d, d, -1, false, false, nullptr };
        stds[p -> _id] = p;
        id[p -> _id] = bag.top(); bag.pop();
        match_let.lock();
        line.insert(p);
    }
    match_let.unlock();
    auto it = line.find(p), next = ++it;
    if (std::abs(p -> t[0] - p -> _t[0]) + std::abs(p -> t[1] - p -> _t[1]) > .000001 && (next == line.end() || !(*next) -> lock)) {
        p -> _t[0] = p -> t[0];
        p -> _t[1] = p -> t[1];
        append(p);
    }

    return p;
}

Std* insert(std::string _id, float args[]) {
    auto slat = args[0], slng = args[1];
    auto tlat = args[2], tlng = args[3];
    int d = args[4];
    Std* p = new Std{ _id, "_", {slat, slng}, {tlat, tlng}, {0, 0}, d, 0, -1, false, false, nullptr };
    id[p -> _id] = bag.top(); bag.pop();
    append(p);
    return p;
}

Std* sell(std::string _id, int length, std::string args[]) {
    // 3 kind of sell no batch, full batch, half batch
    auto porter = stds[_id];
    auto porter_tid = 2 * id[_id] + 1;
    auto p = stds[args[0]];
    int delay = porter -> eta + std::max(p -> d - porter -> eta, d[porter_tid][2 * id[args[0]]]);
    Std* baby = nullptr;
    auto cross = false;
    if (length == 3) {
        baby = stds[args[1]];
        cross = args[2] == "x" ? true : false;
    }
    match_let.lock();
    p -> lock = true;
    if (baby) {
        if (p -> baby) {
            p -> baby -> baby = nullptr;
            p -> baby = nullptr;
        }
        if (baby -> baby) {
            baby -> baby -> baby = nullptr;
            baby -> baby = nullptr;
        }
//        if (p -> baby -> _id != baby -> _id) {
//            p -> baby -> baby = nullptr;
//            if (baby -> baby) baby -> baby -> baby = nullptr;
//        }
        baby -> lock = true;
        p -> baby = baby;
        baby -> baby = p;
        p -> cross = cross;
        baby -> cross = false;
        auto baby_it = line.find(baby);
        if (baby_it != line.end())
            for (; baby_it != line.end() && (*baby_it) -> s[0] + (*baby_it) -> s[1] > .01; )
                baby_it = line.erase(baby_it);
        baby -> porter = _id;
        delay += std::max(baby -> d - porter -> eta - delay, d[2 * id[args[0]]][2 * id[args[1]]]);
        if (cross)
            baby -> eta = delay + d[2 * id[args[1]]][2 * id[args[0]] + 1];
        else
            baby -> eta = delay + d[2 * id[args[1]]][2 * id[args[1]] + 1] + d[2 * id[args[1]] + 1][2 * id[args[0]] + 1];
    } else
        if (p -> baby) {
            p -> baby -> baby = nullptr;
            p -> baby = nullptr;
        }
    auto iterator = line.find(p);
    // if in line and -> porter != _id delete all stds from p to end of porter
    if (iterator != line.end() && (p -> porter != _id || (*std::prev(iterator)) -> s[0] + (*std::prev(iterator)) -> s[1] > .01))
        for (; iterator != line.end() && (*iterator) -> s[0] + (*iterator) -> s[1] > .01; )
            iterator = line.erase(iterator);
    if (iterator == line.end()) {
        p -> porter = _id;
        p -> eta = 0;
        for (auto front = ++line.lower_bound(p); front != line.end() && (*front) -> s[0] + (*front) -> s[1] > .01; )
            front = line.erase(front);
        if (!baby)
            p -> eta = delay + d[2 * id[args[0]]][2 * id[args[0]] + 1];
        else if(cross)
            p -> eta = delay + d[2 * id[args[1]]][2 * id[args[1]] + 1];
        else
            p -> eta = delay + d[2 * id[args[1]]][2 * id[args[0]] + 1] + d[2 * id[args[0]] + 1][2 * id[args[1]] + 1];
        line.insert(p);
    }
//    std::cout << "sell " << _id;
//    show_me();
    check("sell");
    match_let.unlock();
    return p;
}

Std* at(std::string _id, float args[]) {
    auto p = stds[_id];
    auto p_it = line.find(p);
    match_let.lock();
//    if (p_it != line.end()) {
//        (*--p_it) -> lock = true;
//    }
//    std::cout << "at " << _id;
//    show_me();
    check("at");
    match_let.unlock();
    return p;
}

Std* done(std::string _id, float args[]) {
    Std *p = stds[_id], *porter = nullptr;
    bool flag = false;
    match_let.lock();
    if (p == nullptr) std::cout << "he hu hu " << _id << " " << p -> cross << " " << p -> baby -> _id << std::endl;
    if (line.find(p) != line.end()) { // is daddy
        if (p -> baby) {  // daddy with baby,
            auto baby = p -> baby;
            if (baby -> cross == true) {
                flag = true;
                // done both of them let's clean
            } else
                baby -> cross = true;
        } else {  // lone daddy
            flag = true;
            // no baby so let's clean
        }
        porter = *--line.find(p);
    } else {
        if (p -> cross == true) {
            flag = true;
            // done both of them are done now time to clean the mess up
        } else
            p -> cross = true;
        int eta = p -> eta;
        p -> eta = 0;
        porter = *line.upper_bound(p);
        p -> eta = eta;
    }
    if (flag) {
        osm_let.lock();
        auto p_it = line.find(p);
        if (p_it != line.end())
            line.erase(p_it);
        else {
            show_me();
            if (!p -> baby) {
                std::cout << "hiih" << std::endl;
                throw;
            }
            line.erase(line.find(p -> baby));
        }
        stds.erase(_id);
        bag.push(id[_id]);
        id.erase(_id);
        if (p -> baby) {
            std::cout << "^^ " << _id << std::endl;
            stds.erase(p -> baby -> _id);
            bag.push(id[p -> baby -> _id]);
            id.erase(p -> baby -> _id);
            // delete p -> baby;
        }
        // delete p;
        osm_let.unlock();
    }
    match_let.unlock();

    porter -> eta = p -> eta;
    porter -> lock = false;
    int pid = id[porter -> _id] * 2 + 1, tid = id[porter -> _id] * 2 + 1;
    for (auto& it: id) {
        d[pid][it.second * 2] = d[tid][it.second * 2];
        d[pid][it.second * 2 + 1] = d[tid][it.second * 2 + 1];
        d[it.second * 2][pid] = d[it.second * 2][tid];
        d[it.second * 2 + 1][pid] = d[it.second * 2 + 1][tid];
    }
//    std::cout << "done " << _id;
//    show_me();
    check("done");
    return p;
}

int main(int argc, const char *argv[]) {
    const rlim_t kStackSize = 16 * 1024 * 1024;   // min stack size = 16 MB
    struct rlimit rl;
    int result;

    result = getrlimit(RLIMIT_STACK, &rl);
    if (result == 0)
    {
        if (rl.rlim_cur < kStackSize)
        {
            rl.rlim_cur = kStackSize;
            result = setrlimit(RLIMIT_STACK, &rl);
            if (result != 0)
            {
                fprintf(stderr, "setrlimit returned result = %d\n", result);
            }
        }
    }
    for (int i = 0; i < MAX_N; i++)
        bag.push(i);
    methods["location"] = location;
    methods["insert"] = insert;
    methods["remove"] = remove;
    methods["at"] = at;
    methods["done"] = done;
    // methods["report"] = report;

    EngineConfig config;
    config.storage_config = {argv[2]};
    config.use_shared_memory = false;
    config.algorithm = EngineConfig::Algorithm::CH;
    OSRM _osrm = OSRM(config);
    osm = &_osrm;

    std::thread(push_loop).detach();
    std::thread(matching_loop).detach();
    std::thread(osm_loop).detach();

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
        for (buff_p = 0; buff_p <= buff_size; buff_p ++) {
            if (buff[buff_p] == ',' || buff_p == buff_size) {
                if (method == "") method = token;
                else if (_id == "") _id = token;
                else if (method == "sell") sell_args[args_p ++] = token;
                else args[args_p ++] = std::stof(token);
                token = "";
                continue;
            }
            token += buff[buff_p];
        }
        if (method == "sell") sell(_id, args_p, sell_args);
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