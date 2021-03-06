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
#include <deque>
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

/*
for now no familiarity no expected frees
*/

struct Std {
    std::string _id;
    float s[2];
    float t[2];
    float _t[2];
    int d;
    int eta;
    int score;
//    int prev;
//    int idx;
//    int next;
    bool lock;
    bool cross;
//    bool at;
    Std *baby;
    std::deque<Std*> *line;
};

typedef Std* (*FnPtr)(std::string, float []);

tsl::robin_map<std::string, FnPtr> methods;
tsl::robin_map<std::string, Std*> stds;
tsl::robin_map<std::string, int> id;
std::stack<int> bag;
std::vector<std::deque<Std*>*> lines;
// tsl::robin_map<std::string, std::deque<Std*>*> lines;
int d [2 * MAX_N][2 * MAX_N];

std::queue<std::tuple<std::string, Std*>> sells_q;
// std::queue<Std*> dones_q;
bool update_lock, bell;
Clock::time_point update_time_point = Clock::now();
tsl::robin_map<std::string, Std*> update_q;
int _map_to_d[MAX_N], _news_map_to_d[MAX_N];
tsl::robin_map<std::string, tsl::robin_set<std::string>*> checklist;

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

void push() {
    std::vector<std::string> data;
    for (auto const& line : lines)
        if (line -> size() > 1) {
            auto path = line -> at(1);
            std::string paths = line -> front() -> _id + "," + path -> _id;
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
                    path_key = line -> front() -> _id + "," + baby -> _id + "," + "01";
                    baby_key = line -> front() -> _id + "," + path -> _id + "," + "11";
                    flag = true; }
                else {
                    path_key = line -> front() -> _id + "," + baby -> _id + "," + "00";
                    baby_key = line -> front() -> _id + "," + path -> _id + "," + "10";
                }
                if (list -> find(path_key) != list -> end())
                    flag = false;
                else
                    list -> insert(path_key);
                if (baby_list -> find(baby_key) != baby_list -> end())
                    flag = false;
                else
                    baby_list -> insert(baby_key);
            } else {
                if (checklist.find(path -> _id) == checklist.end())
                    checklist[path -> _id] = new tsl::robin_set<std::string> ();
                auto list = checklist[path -> _id];
                if (list -> find(line -> front() -> _id) != list -> end())
                    ;  // flag = false;
                else
                    list -> insert(line -> front() -> _id);
            }
            if (flag) {
                data.push_back(paths);
//                std::cout << "notify " << paths << std::endl;
            }
        }
    // std::cout << "haa ha ha: " << string_join(data, ";") << " ";
//        if (data.size() != 0)
//            std::cout << data[0] << std::endl;
//        else
//            std::cout << std::endl;

    auto post_data = string_join(data, ";");
    if (post_data.length() != 0) {
        CURL *curl;
        CURLcode res;
//        static const char *postthis = ("math" + string_join(data, ";")).c_str();
        data.clear();
        curl = curl_easy_init();
        if(curl) {
//            std::cout << postthis << std::endl;
            curl_easy_setopt(curl, CURLOPT_URL, ("http://localhost/v0.2/" + hang + "/!!!/NN").c_str());
            curl_easy_setopt(curl, CURLOPT_POSTFIELDS, post_data.c_str());
            curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, post_data.length());
            res = curl_easy_perform(curl);
//            if(res != CURLE_OK)
//                fprintf(stderr, "curl_easy_perform() failed: %s\n", curl_easy_strerror(res));
//            std::cout << res << std::endl;
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

void batch() {
    // you know if v matched u then u must match v -> sort with edge weight then iterate add u and v to set.
    std::cout << "batching" << std::endl;
    std::vector <Std*> paths;
    for (const auto &it : stds) {
        auto p = it.second;
        if (std::abs(p -> s[0]) + std::abs(p -> s[1]) > .1)
            paths.push_back(p);
    }
//    for (const auto &it : paths)
//        std::cout << it -> _id << ", ";
//    std::cout << std::endl;

    auto n_dim = (int) paths.size();
    float cost [n_dim][n_dim];
    bool crosses [n_dim][n_dim];
    int rowsol[n_dim];
    int colsol[n_dim];
    float u[n_dim];
    float v[n_dim];
    tsl::robin_set<std::string> parents, babies;
    for (int i = 0; i < n_dim; i ++) {
        u[i] = .0;
        v[i] = .0;
        parents.insert(paths[i] -> _id);
        babies.insert(paths[i] -> _id);
    }

    for (int i = 0; i < n_dim; i ++) {
        auto vp = paths[i];
        if (vp -> lock) babies.erase(vp -> _id);
        if (vp -> baby) {
            if (vp -> lock && vp -> baby -> lock) {
                parents.erase(vp -> baby -> _id);
                parents.erase(vp -> _id);
                parents.erase(vp -> baby -> _id);
                babies.erase(vp -> _id);
                babies.erase(vp -> baby -> _id);
            } else
                vp -> baby = 0;
        }
        for (int j = 0; j < n_dim; j ++) {
            auto up = paths[j];
            auto v_id = id[vp -> _id], u_id = id[up -> _id];
            auto delay = up -> d - vp -> d;
            delay = std::max(delay, d[2 * v_id][2 * u_id]);
            auto straight = delay + d[2 * u_id][2 * u_id + 1] + d[2 * u_id + 1][2 * v_id + 1]; // without d
            auto cross = delay + d[2 * u_id][2 * v_id + 1] + d[2 * v_id + 1][2 * u_id + 1];
            // you can define a threshold for both of them else inf. (and have to, must)
            if (i == j || up -> lock || std::min(straight, cross) > (d[2 * v_id][2 * v_id + 1] + d[2 * u_id][2 * u_id + 1]) * 3 / 2 + std::max(0, up -> d - vp -> d) / 2)
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
//    for (int i = 0; i < n_dim; i ++) {
//        for (int j = 0; j < n_dim;j ++)
//            std::cout << cost[i][j] << ' ';
//        std::cout << std::endl;
//    }
    auto cost_matrix = reinterpret_cast<float*>(cost);
    lap(n_dim, cost_matrix, 0, rowsol, colsol, u, v);  // verbose = 0
    std::vector <std::tuple<float, int, int>> result;

//    for (int i = 0; i < n_dim; i ++)
//        std::cout << rowsol[i] << " ";
//
//    std::cout << std::endl;

    for (int i = 0; i < n_dim; i ++)
        result.push_back(std::make_tuple(cost[i][rowsol[i]], i, rowsol[i]));
    sort(result.begin(), result.end());  // todo sort with v.lock == true first also if at of parent is true we cant batch, also we can reduce cost of them.

    for (int i = 0; i < n_dim; i ++)
        if (std::get<0>(result[i]) < std::numeric_limits<int>::max() / 2) {
            auto v_idx = std::get<1>(result[i]), u_idx = std::get<2>(result[i]);
            // std::cout << v_idx << " " << u_idx << std::endl;
            if (parents.find(paths[v_idx] -> _id) != parents.end() && babies.find(paths[u_idx] -> _id) != babies.end()) {
                // std::cout << "hu hu" << std::endl;
                auto vp = paths[v_idx], up = paths[u_idx];
                parents.erase(vp -> _id);
                parents.erase(up -> _id);
                babies.erase(vp -> _id);
                babies.erase(up -> _id);

                auto cross = crosses[v_idx][u_idx];
                vp -> baby = up;
                // std::cout << "- " << vp -> baby << ", " << vp -> _id << std::endl;
                vp -> cross = cross;
            }
        }
    for (auto const &it : stds) {
        auto p = it.second;
//        std::cout << "+ " << p -> baby << ", " << p -> _id << std::endl;
        if (p -> baby)
            ;  // std::cout << p -> _id << " -> " << p -> baby -> _id << std::endl;
    }
    std::cout << "batching done" << std::endl;
}

void match(int undo, int redo) {
//    std::cout << "start matching" << std::endl;
    if (bell) {
        undo = (int) stds.size();
        redo = (int) stds.size() * 2;
    }
    tsl::robin_map<std::string, Std*> sells;
    while (!sells_q.empty()) {
        auto porter_id = std::get<0>(sells_q.front());
        auto path = std::get<1>(sells_q.front());
        if (path -> line)
            while (path -> line -> size() > 1 && path -> line -> back() -> _id != path -> _id) {
                if (undo)
                    undo --;
                else
                    redo ++;
                path -> line -> back() -> line = nullptr;
                path -> line -> back() -> eta = 0;
                path -> line -> pop_back();

            }
        sells[porter_id] = path;
        sells_q.pop();
    }
//    std::cout << "size of sells :  " << sells.size() << std::endl;
    for (auto const& line : lines) {
        auto porter_id = line -> front() -> _id;
        if (sells.find(porter_id) != sells.end()) {
            auto path = sells[porter_id];
            path -> line = line;
            if (path -> baby)
                path -> baby -> line = line;
            // hamasho mirizim birun hey undo --; va ella redo ++;
            while(line -> size() > 1 && line -> back() -> _id != path -> _id) {
                if (undo)
                    undo --;
                else
                    redo ++;
                line -> back() -> line = nullptr;
                line -> back() -> eta = 0;
                line -> pop_back();
            }
            if (line -> size() <= 1 || line -> back() -> _id != path -> _id) {
                line -> push_back(path);
                path -> line = line;
                auto head_id = id[line -> front() -> _id], path_id = id[path -> _id];
                auto delay = std::abs(path -> d - line -> front() -> eta);
                path -> eta = line -> front() -> eta + std::max(delay, d[2 * head_id + 1][2 * path_id]) + d[2 * path_id][2 * path_id + 1];  // todo sorry it is wrong when baby.
            }
            if (line -> size() != 2) {
                for (auto const &p : *line)
                    std::cout << p -> _id << " * " << p -> lock << std::endl;
                throw;
            }
        }
    }
//    if (bell)
//        batch();
    // #2 a max heap with score in Std each time pop from heap, heap.insert(popped.prev)

    for (auto const& line : lines)
        while(undo && line -> size() > 1 && !(line -> back() -> lock)) {
            undo --;
            line -> back() -> line = nullptr;
            line -> back() -> eta = 0;
            line -> pop_back();
        }
    for (const auto &it : sells) {
        it.second -> lock = true;
        if (it.second -> baby) it.second -> baby -> lock = true;
    }
    redo -= undo;

    tsl::robin_set<std::string> orphans;
    for (auto const& line : lines)
        for (auto const& p : *line)
            orphans.insert(p -> _id);

    for (auto const &it : stds)
        if (orphans.find(it.first) != orphans.end())
            orphans.erase(it.first);
        else
            orphans.insert(it.first);
    if (lines.size() == 0 || orphans.size() == 0) return;

//    std::cout << "All Orphans: " << orphans.size() << std::endl;
//    for (auto const& it : orphans)
//        std::cout << it << ", ";
//    std::cout << std::endl;
//
//    std::cout << "          ";
//    for (auto const &col : stds) {
//        std::cout << col.first << " ";
//    }
//    std::cout << std::endl;
//
//    for (auto const &row : stds) {
//        std::cout << row.firsts << " ";
//        for (auto const &col : stds)
//            std::cout << d[2 * id[row.first] + 1][2 * id[col.first]] << " ";
//        std::cout << std::endl;
//    }
    Std* orphans_array[orphans.size()];
//    int nn = 0;
    while (redo && (int) orphans.size()/*  && nn ++ < 1 */) {
//        std::cout << redo << ", " << (int) lines.size() << ", " << (int) orphans.size() << std::endl;
        int n_dim = std::max(lines.size(), orphans.size());  // (heads_size, orphans.size());
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

        int i = 0;
        for (auto const &orphan_name : orphans)
            orphans_array[i ++] = stds[orphan_name];

        // DONE order of orphans is not granted NOW granted
        i = 0;
//        std::cout << "yesss" << std::endl;

        try {
            for (auto const &line : lines) {
    //            if (!line -> empty())
    //                for (auto const &p : *line)
    //                    std::cout << p -> _id << " > ";
                auto head = line -> back();
//                std::cout << /* std::endl << */ line -> size() << " ~ " << head << " ~ " << head -> _id << std::endl;

                    for (int j = 0; j < orphans.size(); j ++) {
        //                std::cout << orphans_array[j] << " -> ";
        //                std::cout << orphans_array[j] -> _id;
                        auto orphan = orphans_array[j];
        //                std::cout << " |";
                        auto delay = head -> eta;
                        if (head -> baby && head -> cross) delay = head -> baby -> eta;
                        delay = std::abs(orphan -> d - delay);  // std::abs removed
        //                delay = 0;  // todo relax just for debugging
        //                std::cout << "| ";
                        cost[i][j] = std::max(delay, d[2 * id[head -> _id] + 1][2 * id[orphan -> _id]]);
                    }
                    i ++;

            }
        } catch(int e) {
            std::cout << "haa ha ha" << std::endl;
            throw;
        }
//        std::cout << "here" << std::endl;
//        for (int i = 0; i < n_dim; i ++) {
//            for (int j = 0; j < n_dim;j ++)
//                std::cout << cost[i][j] << ' ';
//            std::cout << std::endl;
//        }

        auto cost_matrix = reinterpret_cast<float*>(cost);
        lap(n_dim, cost_matrix, 0, rowsol, colsol, u, v);  // verbose = 0

//        for (int i = 0; i < n_dim; i ++)
//            std::cout << rowsol[i] << " ";
//        std::cout << std::endl;
//        std::cout << std::endl;

        std::vector <std::tuple<float, int, int>> result;
        for (int i = 0; i < lines.size(); i ++)
            result.push_back(std::make_tuple(cost[i][rowsol[i]], i, rowsol[i]));
        sort(result.begin(), result.end());  // todo sort with v.lock == true first also if at of parent is true we cant batch, also we can reduce cost of them.

//        for (int i = 0; i < lines.size(); i ++)
//            std::cout << "tuple: " << std::get<0>(result[i]) << " " << std::get<1>(result[i]) << " " << std::get<2>(result[i]) << std::endl;

        for (int i = 0; i < lines.size() && redo && orphans.size(); i ++) {
//            auto weight = std::get<0>(result[i]);
            auto head = lines[std::get<1>(result[i])] -> back();
            auto candidate = orphans_array[std::get<2>(result[i])];
//            if (std::abs(head -> s[0]) + std::abs(head -> s[1]) < .0001)
//                std::cout << head -> _id << " -> " << candidate -> _id << std::endl;
//            std::cout << "size before: " << orphans.size() << std::endl;
            orphans.erase(candidate -> _id);
//            std::cout << "size after: " << orphans.size() << std::endl;
            auto d_id = id[candidate -> _id];
            candidate -> eta = head -> eta + cost[std::get<1>(result[i])][std::get<2>(result[i])] + d[2 * d_id][2 * d_id + 1];  // todo sorry it is wrong when baby.
            lines[std::get<1>(result[i])] -> push_back(candidate);
            candidate -> line = lines[std::get<1>(result[i])];
            redo --;
        }

        // TODO so simple we just push all. with out sorting two problem one the line is not sorted for now
    }
//    for (auto const &line : lines) {
//        if (line -> size() > 1)
//            std::cout << line -> front() -> _id << " -> " << line -> at(1) -> _id << ", " << line -> at(1) -> lock << std::endl;
//        else
//            std::cout << line -> front() -> _id << std::endl;
//    }
//    std::cout << "*******************" << std::endl;
    tsl::robin_set<std::string> set;
    for (auto const &line : lines)
        for (auto const &p : *line) {
            if (set.find(p -> _id) != set.end()) {
                std::cout << " double trouble " << p -> _id << std::endl;
                throw;
            } else
                set.insert(p -> _id);
        }
    if (set.size() != stds.size()) {
        std::cout << " UnSized stds, set = " << stds.size() << ", " << set.size() << std::endl;
        auto _now = std::chrono::system_clock::now();
        int now = std::chrono::system_clock::to_time_t( _now );
        std::cout << now << std::endl;
        for (auto const &it : stds)
            if (set.find(it.first) == set.end())
                std::cout << it.second -> _id << ", " << it.second -> lock << ", " << it.second -> line << ", " << it.second -> d << std::endl;
        // throw;
    }
    std::thread(push).detach();
//
//    for (auto const *line : lines)
//        if (line -> size() == 1)
//            std::cout << line -> front() -> _id << " ";
//    std::cout << std::endl;
}

void matching_loop() {
    while (true) {
        if (!sells_q.empty() /* || dones_q.size() */ || bell)
            match(stds.size(), 2 * stds.size());
        bell = false;
        std::this_thread::sleep_for(std::chrono::milliseconds(1000));
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
        // std::cout << _id << std::endl;
        forward.coordinates.push_back({util::FloatLongitude{one_all -> s[1]}, util::FloatLatitude{one_all -> s[0]}});
        forward.coordinates.push_back({util::FloatLongitude{one_all -> t[1]}, util::FloatLatitude{one_all -> t[0]}});
        backward.coordinates.push_back({util::FloatLongitude{one_all -> s[1]}, util::FloatLatitude{one_all -> s[0]}});
        backward.coordinates.push_back({util::FloatLongitude{one_all -> t[1]}, util::FloatLatitude{one_all -> t[0]}});

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

    for (auto const& it : update_q) {
        auto one_all = it.second;
        auto _id = it.first;
        if (stds.find(_id) == stds.end()) {
            forward.coordinates.push_back({util::FloatLongitude{one_all -> s[1]}, util::FloatLatitude{one_all -> s[0]}});
            forward.coordinates.push_back({util::FloatLongitude{one_all -> t[1]}, util::FloatLatitude{one_all -> t[0]}});
            backward.coordinates.push_back({util::FloatLongitude{one_all -> s[1]}, util::FloatLatitude{one_all -> s[0]}});
            backward.coordinates.push_back({util::FloatLongitude{one_all -> t[1]}, util::FloatLatitude{one_all -> t[0]}});

            forward.destinations.push_back(2 * ptr);
            forward.destinations.push_back(2 * ptr + 1);
            backward.sources.push_back(2 * ptr);
            backward.sources.push_back(2 * ptr + 1);

                forward.sources.push_back(2 * ptr);
                forward.sources.push_back(2 * ptr + 1);
                backward.destinations.push_back(2 * ptr);
                backward.destinations.push_back(2 * ptr + 1);
                _news_map_to_d[news_ptr ++] = id[_id];


            _map_to_d[ptr ++] = id[_id];
        }
    }

    json::Object forward_result, backward_result;
    const auto forward_status = osm -> Table(forward, forward_result);
    const auto backward_status = osm -> Table(backward, backward_result);

    auto &forward_durations = forward_result.values["durations"].get<json::Array>().values;
    auto &backward_durations = backward_result.values["durations"].get<json::Array>().values;

    // std::cout << durations.front().get<json::Array>().values.at(1).get<json::Number>().value << "\n";
    // update d for both forward and backward
    // std::cout << forward_durations.size() << " " << backward_durations.size() << std::endl;
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

    for (auto const& it : update_q) stds[it.first] = it.second;
    update_q.clear(); // If needed.
    update_time_point = Clock::now();
    update_lock = false;

//    std::thread(match, stds.size(), stds.size()).detach();
    bell = true;
}

void update_d(Std* p) {
    update_q[p -> _id] = p;
    int delay = 1000 * 6 * exp(-7 / 10 * sqrt(update_q.size())) + 333;
    Clock::time_point now = Clock::now();
    Clock::time_point _update_time_point = now + std::chrono::milliseconds(delay);
    if (update_time_point < now || _update_time_point < update_time_point) {
        update_time_point = _update_time_point;
        std::thread t = std::thread(_update, delay);
        t.detach();
    }
}

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
        p -> eta = d;
    } else {
        std::deque<Std*>* line = new std::deque<Std*>();
        p = new Std{ _id, {0, 0}, {lat, lng}, {0, 0}, d, d, -1, false, false, nullptr, line };
        stds[p -> _id] = p;
        id[p -> _id] = bag.top(); bag.pop();
        line -> push_back(p);
        lines.push_back(line);
    }
    if (std::abs(p -> t[0] - p -> _t[0]) + std::abs(p -> t[1] - p -> _t[1]) > .000001 && (p -> line -> size() == 1 || !p -> line -> operator[](1) -> lock)) {
        p -> _t[0] = p -> t[0];
        p -> _t[1] = p -> t[1];
        update_d(p);
    }

    return p;
}

Std* insert(std::string _id, float args[]) {
    auto slat = args[0], slng = args[1];
    auto tlat = args[2], tlng = args[3];
    int d = args[4];
    Std* p = new Std{ _id, {slat, slng}, {tlat, tlng}, {0, 0}, d, 0, -1, false, false, nullptr };
    // stds[std._id] = std;
    id[p -> _id] = bag.top(); bag.pop();
    update_d(p);
    return p;
}

Std* sell(std::string _id, int length, std::string args[]) {  // no need for anything with topology we can find if it is batch and who is, KHAFE baba
    auto p = stds[args[0]];
//    p -> lock = true;
    if (length == 3) {
        auto baby = stds[args[1]];
        p -> baby = baby;
//        baby -> lock = true;
        p -> cross = args[2] == "x" ? true : false;
    }
    sells_q.push(make_tuple(_id, p));
//    std::cout << "size of sell_q: " << sells_q.size() << std::endl;
    // if its prev and baby was not true -> add to q of match() -> match it self reposition them -> rematch all in a thread
    return p;
}

Std* at(std::string _id, float args[]) {
    auto p = stds[_id];
//    std::cout << "the line: " << p -> line << std::endl;
    p -> line -> front() -> lock = true;
    return p;
}

Std* done(std::string _id, float args[]) {
    Std* p = stds[_id];
    bool flag = false;
    if (p -> line -> at(1) -> _id == p -> _id) { // is daddy
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
    } else {
        if (p -> cross == true) {
            flag = true;
            // done both of them are done now time to clean the mess up
        } else
            p -> cross = true;
    }
    if (flag) {  // in match or here
//        for (auto const &ptr : *p -> line)
//            std::cout << ptr -> _id << " " << ptr -> lock << " ";
//        std::cout << std::endl;
        auto porter = p -> line -> front();
        p -> line -> pop_front();
        p -> line -> operator[](0) = porter;
        stds.erase(_id);
        bag.push(id[_id]);
        id.erase(_id);
//        for (auto const &ptr : *p -> line)
//            std::cout << ptr -> _id << " " << ptr -> lock << " ";
//        std::cout << std::endl;
//        dones_q.push(p);
    }

    // copy ds of loc with it's
    Std par = *p -> line -> front();
    p -> line -> front() -> eta = p -> eta;
    int pid = id[par._id] * 2 + 1, tid = id[par._id] * 2 + 1;
    for (auto& it: id) {
        d[pid][it.second * 2] = d[tid][it.second * 2];
        d[pid][it.second * 2 + 1] = d[tid][it.second * 2 + 1];
        d[it.second * 2][pid] = d[it.second * 2][tid];
        d[it.second * 2 + 1][pid] = d[it.second * 2 + 1][tid];
    }

    return p;
}

Std* report(std::string _id, float args[]) {
    if (stds.find(_id) == stds.end()) {
        std::cout << "not found" << std::endl;
        return nullptr;
    }
    auto line = stds[_id] -> line;
    for (auto const &ptr : *line)
        std::cout << ptr -> _id << " " << ptr -> lock << " ";
    std::cout << std::endl;
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
    stds[p0._id] = &p0;
    id[p0._id] = bag.top(); bag.pop();
    // line.push_back(&p0);

    Std p1 = {
        ._id = "1",
    };
    p1.s[0] = 35.749913;
    p1.s[1] = 51.420229;
    p1.d = now + 5;
    stds[p1._id] = &p1;
    id[p1._id] = bag.top(); bag.pop();
    // line.push_back(&p1);

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
    methods["report"] = report;

    EngineConfig config;
    config.storage_config = {argv[2]};
    config.use_shared_memory = false;
    config.algorithm = EngineConfig::Algorithm::CH;
    OSRM _osrm = OSRM(config);
    osm = &_osrm;

    std::thread(push_loop).detach();
    std::thread(matching_loop).detach();

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