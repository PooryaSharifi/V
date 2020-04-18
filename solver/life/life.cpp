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
std::string hang, solver;

struct Std {
    std::string _id;
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

typedef Std* (*FnPtr)(std::string, float []);
tsl::robin_map<std::string, FnPtr> methods;
tsl::robin_map<std::string, Std*> stds;
tsl::robin_map<std::string, int> id;
std::stack<int> bag;
int d [2 * MAX_N][2 * MAX_N];
tsl::robin_map<std::string, std::deque<Std*>*> lines, heads, future;
tsl::robin_map<std::string, Std*> orphans;

std::mutex osm_let, match_let;

tsl::robin_map<std::string, Std*> *stds_q = new tsl::robin_map<std::string, Std*>();
TableParameters *forward = new TableParameters(), *backward = new TableParameters();
std::vector<int> *map_to_d = new std::vector<int>();

tsl::robin_map<std::string, tsl::robin_set<std::string>*> checklist;

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

void show_me(std::string action) {
    std::cout << action << std::endl;
    for (auto const &it : future) {
        auto real = heads[it.first], imagination = it.second;
        for (auto const &p : *real) {
            if (p -> s[0] + p -> s[1] < .01)
                std::cout << (p -> lock ? "@ " : "* ");
            else
                std::cout << (p -> lock ? ">" : "");
            std::cout << p -> _id;
            if (p -> baby)
                std::cout << " ^ " << p -> baby -> _id << " - ";
            std::cout << " - ";
        }
        std::cout << "| ";
        for (auto const &p : *imagination) {
            std::cout << p -> _id;
            if (p -> baby)
                std::cout << " ^ " << p -> baby -> _id << " - ";
            std::cout << " - ";
        }
        std::cout << std::endl;
    }
    for (auto const &it : orphans) {
        std::cout << it.first << " ";
        if (it.second -> baby)
            std::cout << "^ " << it.second -> baby -> _id << " ";
    }
    std::cout << std::endl;
}

void push() {
    std::vector<std::string> data;
    match_let.lock();
    for (auto const &it : future) {
        auto porter = it.first;
        auto line = it.second;
        if (!line -> empty() && heads[porter] -> size() == 1) {
            auto path = line -> front();
            std::string paths = porter + "," + path -> _id;
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
                    path_key = porter + "," + baby -> _id + "," + "01";
                    baby_key = porter + "," + path -> _id + "," + "11";
                    flag = true;
                } else {
                    path_key = porter + "," + baby -> _id + "," + "00";
                    baby_key = porter + "," + path -> _id + "," + "10";
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
                if (list -> find(porter) != list -> end())
                    ; //flag = false;
                else
                    list -> insert(porter);
            }
            if (flag)
                data.push_back(paths);
        }
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

void reflex(int n_dim, float *cost, int verbose, int *rowsol, int *colsol, float *u, float *v) {
    // i suppose it is type of heads * orphans with size of n_dim;
//    for (int i=0;i<n_dim;i++) {
//        for (int j=0;j<n_dim;j ++)
//            std::cout << cost[i * n_dim + j] << " ";
//        std::cout << std::endl;
//    }
    tsl::robin_set<int> ints;
    for (int i = 0; i < n_dim; i ++) ints.insert(i);
    for (int j = 0; j < n_dim; j ++) {
        float weights[6] = {
            (float) std::numeric_limits<int>::max(),
            (float) std::numeric_limits<int>::max(),
            (float) std::numeric_limits<int>::max(),
            (float) std::numeric_limits<int>::max(),
            (float) std::numeric_limits<int>::max(),
            (float) std::numeric_limits<int>::max()
        };
        int idx[6] = {-1, -1, -1, -1, -1, -1};
        for (int i = 0; i < n_dim; i ++) {
            weights[5] = cost[i * n_dim + j];
            idx[5] = i;
            for (int k = 5; k > 0; k --)
                if (weights[k] < weights[k - 1]) {
                    auto w = weights[k];
                    auto x = idx[k];
                    weights[k] = weights[k - 1];
                    idx[k] = idx[k - 1];
                    weights[k - 1] = w;
                    idx[k - 1] = x;
                }
        }
        int ii = -1;
        for (int k = 0; k < 5; k ++)
            if (weights[k] < (float) std::numeric_limits<int>::max() && ints.find(idx[k]) != ints.end()) {
                ii = idx[k];
                break;
            }
        if (ii == -1) {
            auto head = ints.begin();
            ii = *head;
            ints.erase(head);
        }
        rowsol[ii] = j;
        ints.erase(ii);
        for (int jj = 0; jj < n_dim; jj ++)
            if (j != jj)
                cost[ii * n_dim + jj] = (float) std::numeric_limits<int>::max() / 2;
    }
}

void batch() {
    match_let.lock();
    auto n_dim = orphans.size() + 0;
    std::vector<Std*> parents, babies;
    float cost [n_dim][n_dim];
    bool crosses [n_dim][n_dim];
    int rowsol[n_dim], colsol[n_dim];
    float u[n_dim], v[n_dim];
    for (int i = 0; i < n_dim; i ++) { u[i] = .0; v[i] = .0; }
    for (auto const &it : orphans) {
        parents.push_back(it.second);
        babies.push_back(it.second);
    }
    match_let.unlock();
    for (int i = 0; i < n_dim; i ++)
        for (int j = 0; j < n_dim; j ++) {
            auto vp = parents[i], up = babies[j];
            auto v_id = id[vp -> _id], u_id = id[up -> _id];

            auto delay = up -> d - vp -> d;
            delay = std::max(delay, d[2 * v_id][2 * u_id]);
            auto straight = delay + d[2 * u_id][2 * u_id + 1] + d[2 * u_id + 1][2 * v_id + 1];
            auto cross = delay + d[2 * u_id][2 * v_id + 1] + d[2 * v_id + 1][2 * u_id + 1];

            if (vp -> _id == up -> _id || std::min(straight, cross) > (d[2 * v_id][2 * v_id + 1] + d[2 * u_id][2 * u_id + 1]) * 5 / 4 + std::max(0, up -> d - vp -> d) / 4)
                cost[i][j] = (int) std::numeric_limits<int>::max();
            else if (cross < straight) {
                cost[i][j] = cross;
                crosses[i][j] = true;
            } else {
                cost[i][j] = straight;
                crosses[i][j] = false;
            }
        }

    lap(n_dim, reinterpret_cast<float*>(cost), 0, rowsol, colsol, u, v);  // verbose = 0
    std::vector <std::tuple<float, int, int>> result;
    for (int i = 0; i < n_dim; i ++)
        result.push_back(std::make_tuple(cost[i][rowsol[i]], i, rowsol[i]));
    sort(result.begin(), result.end());
    while (!result.empty() && std::get<0>(result.back()) > (int) std::numeric_limits<int>::max() / 2) result.pop_back();
    match_let.lock();
    for (int i = 0; i < result.size(); i ++) {
        auto v_idx = std::get<1>(result[i]), u_idx = std::get<2>(result[i]);
        auto vp = parents[v_idx], up = babies[u_idx];
        if (!vp -> baby && !up -> baby && !up -> lock && orphans.find(vp -> _id) != orphans.end() && orphans.find(up -> _id) != orphans.end()) {
            auto cross = crosses[v_idx][u_idx];
            vp -> baby = up;
            up -> baby = vp;
            vp -> cross = cross;
            up -> cross = cross;
            orphans.erase(up -> _id);
        }
    }
    match_let.unlock();
}

bool match() {
    osm_let.lock();
    match_let.lock();
    int n_dim = std::max(future.size(), orphans.size());
    std::string orphans_list[n_dim], future_list[n_dim];
    float cost [n_dim][n_dim];
    int rowsol[n_dim], colsol[n_dim];
    float u[n_dim], v[n_dim];
    for (int i = 0; i < n_dim; i ++) { u[i] = .0; v[i] = .0; }
    for (int i = 0; i < n_dim; i ++)
        for (int j = 0; j < n_dim; j ++)
            cost[i][j] = std::numeric_limits<int>::max();

    int i = 0, j = 0;
    for (auto const &it : future) {
        auto head = it.second -> empty() ? heads[it.first] -> back() : it.second -> back();
        future_list[i] = it.first;
        for (auto const &oit : orphans) {
            auto orphan = oit.second;
//            int delay = head -> eta;
//             if (head -> baby && head -> cross) delay = head -> baby -> eta;
            delay = orphan -> d - head -> eta;  // std::abs
            orphans_list[j] = orphan -> _id;
            cost[i][j ++] = std::max(std::max(delay, head -> s[0] + head -> s[1] < .01 || solver != "grd" ? 0 : std::numeric_limits<int>::max() / 2), d[2 * id[head -> _id] + 1][2 * id[orphan -> _id]]);
        }
        i ++; j = 0;
    }
    match_let.unlock();
    osm_let.unlock();

    if (solver == "grd") reflex(n_dim, reinterpret_cast<float*>(cost), 0, rowsol, colsol, u, v);
    else lap(n_dim, reinterpret_cast<float*>(cost), 0, rowsol, colsol, u, v);

    std::vector <std::tuple<float, int, int>> result;
    for (int i = 0; i < n_dim; i ++)
        result.push_back(std::make_tuple(cost[i][rowsol[i]], i, rowsol[i]));
    sort(result.begin(), result.end());
    while (std::get<0>(result.back()) > (int) std::numeric_limits<int>::max() / 4) result.pop_back();

    match_let.lock();
    for (auto const &m : result) {
        auto porter_id = future_list[std::get<1>(m)], orphan_id = orphans_list[std::get<2>(m)];
        if (orphans.find(orphan_id) != orphans.end() && future.find(porter_id) != future.end()) {
            auto line = future[porter_id];
            auto head = line -> empty() ? heads[porter_id] -> back() : line -> back(), orphan = orphans[orphan_id];
            orphans.erase(orphan_id); line -> push_back(orphan); lines[orphan_id] = line;
            auto d_id = id[orphan -> _id];
            auto arrival = std::max(orphan -> d, head -> eta + d[2 * id[head -> _id] + 1][2 * d_id]);
            if (orphan -> baby) {
                lines[orphan -> baby -> _id] = line;
                auto b_id = id[orphan -> baby -> _id];
                arrival = std::max(orphan -> baby -> d, arrival + d[2 * d_id][2 * b_id]);
                if (orphan -> cross) {
                    orphan -> eta = arrival + d[2 * b_id][2 * d_id + 1];
                    orphan -> baby -> eta = arrival + d[2 * b_id][2 * d_id + 1] + d[2 * d_id + 1][2 * b_id + 1];
                } else {
                    orphan -> eta = arrival + d[2 * b_id][2 * b_id + 1] + d[2 * b_id + 1][2 * d_id + 1];
                    orphan -> baby -> eta = arrival + d[2 * b_id][2 * b_id + 1];
                }
            } else
                orphan -> eta = arrival + d[2 * d_id][2 * d_id + 1];
        }
    }
    match_let.unlock();
    return solver == "grd" ? false : true;
}

void imagine() {
    match_let.lock();
    for (auto const &it : future) {
        auto line = it.second;
        while (!line -> empty()) {
            auto p = line -> back(); line -> pop_back();
            lines.erase(lines.find(p -> _id));
            orphans[p -> _id] = p;
            if (p -> baby) {
                lines.erase(lines.find(p -> baby -> _id));
                orphans[p -> baby -> _id] = p -> baby;
                p -> baby -> baby = nullptr;
                p -> baby = nullptr;
            }
        }
    }
    match_let.unlock();
    if (solver == "bng") batch();
    while (!future.empty() && !orphans.empty() && match());
}

void imagination_loop() {
    while (true) {
        imagine();
        std::this_thread::sleep_for(std::chrono::milliseconds(3000));
    }
}

void route() {
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
    osm_let.lock();
    match_let.lock();
    for (auto const& it : *_stds_q) {
        auto p = it.second;
        stds[it.first] = it.second;
        if (p -> s[0] + p -> s[1] > .01)
            orphans[p -> _id] = p;
    }
    match_let.unlock();
    osm_let.unlock();

    delete _stds_q;
    delete _forward;
    delete _backward;
    delete _map_to_d;
}

void router_loop() {
    while (true) {
        if (!stds_q -> empty()) route();
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
    Std* p = nullptr;
    osm_let.lock();
    if (stds_q -> find(_id) != stds_q -> end()) p = stds_q -> operator[](_id);
    if (stds.find(_id) != stds.end()) p = stds[_id];
    if (p) {
        p -> t[0] = lat; p -> t[1] = lng;
        p -> d = d;
        p -> eta = d;
    } else {
        p = new Std{ _id, {0, 0}, {lat, lng}, {0, 0}, d, d, -1, false, false, nullptr };
        auto dream = new std::deque<Std*>(), real = new std::deque<Std*>();
        match_let.lock();
        future[_id] = dream;
        heads[_id] = real; real -> push_back(p);
        id[p -> _id] = bag.top(); bag.pop();
        match_let.unlock();
    }
    osm_let.unlock();
    if (std::abs(p -> t[0] - p -> _t[0]) + std::abs(p -> t[1] - p -> _t[1]) > .000001 && heads[_id] -> size() == 1) {
        p -> _t[0] = p -> t[0];
        p -> _t[1] = p -> t[1];
        append(p);
    }
//    show_me("location");
    return p;
}

Std* insert(std::string _id, float args[]) {
    auto slat = args[0], slng = args[1];
    auto tlat = args[2], tlng = args[3];
    int d = args[4];
    Std* p = new Std{ _id, {slat, slng}, {tlat, tlng}, {0, 0}, d, 0, -1, false, false, nullptr };
    id[p -> _id] = bag.top(); bag.pop();
    append(p);
//    show_me("insert");
    return p;
}

Std* sell(std::string _id, int length, std::string args[]) {
    // 3 kind of sell no batch, full batch, half batch
    auto porter = stds[_id];
    auto porter_tid = 2 * id[_id] + 1;
    auto p = stds[args[0]];
    int delay = std::max(p -> d, porter -> eta + d[porter_tid][2 * id[args[0]]]);
    Std* baby = nullptr;
    auto cross = false;
    match_let.lock();
    if (orphans.find(args[0]) != orphans.end()) orphans.erase(args[0]);
    if (lines.find(args[0]) != lines.end()) {
        auto line = lines[args[0]];
        do {
            if (line -> back() -> baby) {
                auto baby = line -> back() -> baby;
                lines.erase(lines.find(baby -> _id));
                if (baby -> _id != args[0])
                    orphans[baby -> _id] = baby;
                baby -> baby = nullptr;
                line -> back() -> baby = nullptr;
            } else {
                lines.erase(lines.find(line -> back() -> _id));
                if (line -> back() -> _id != args[0])
                    orphans[line -> back() -> _id] = line -> back();
                line -> pop_back();
            }
        } while (lines.find(args[0]) != lines.end());  // line -> back() -> _id != args[0] && (!line -> back() -> baby || line -> back() -> baby -> _id != args[0]
    }
    if (length == 3) {
        baby = stds[args[1]];
        if (orphans.find(args[1]) != orphans.end()) orphans.erase(args[1]);
        if (lines.find(args[1]) != lines.end()) {
            auto line = lines[args[1]];
            do {
                try {
                    if(line -> back() -> baby) std::cout << "heh" << std::endl;
                } catch (int e) {
                    std::cout << line -> size() << " " << _id << " " << args[0] << std::endl;
                    show_me("error");
                    throw;
                }
                if (line -> back() -> baby) {
                    auto baby = line -> back() -> baby;
                    lines.erase(baby -> _id);
                    if (baby -> _id != args[1])
                        orphans[baby -> _id] = baby;
                    baby -> baby = nullptr;
                    line -> back() -> baby = nullptr;
                } else {
                    lines.erase(line -> back() -> _id);
                    if (line -> back() -> _id != args[1])
                        orphans[line -> back() -> _id] = line -> back();
                    line -> pop_back();
                }
            } while (lines.find(args[1]) != lines.end());
        }
        cross = args[2] == "x" ? true : false;
    }
    p -> lock = true;
    auto h_line = heads[_id];
    h_line -> push_back(p);
    heads[args[0]] = h_line;
    if (baby) {
        baby -> lock = true;
        heads[args[1]] = h_line;
        p -> baby = baby;
        baby -> baby = p;
        p -> cross = cross;
        baby -> cross = cross;
        delay = std::max(baby -> d, delay + d[2 * id[args[0]]][2 * id[args[1]]]);
        if (cross) {
            p -> eta = delay + d[2 * id[args[1]]][2 * id[args[0]] + 1];
            baby -> eta = delay + d[2 * id[args[1]]][2 * id[args[0]] + 1] + d[2 * id[args[0]] + 1][2 * id[args[1]] + 1];
        } else {
            p -> eta = delay + d[2 * id[args[1]]][2 * id[args[1]] + 1] + d[2 * id[args[1]] + 1][2 * id[args[0]] + 1];
            baby -> eta = delay + d[2 * id[args[1]]][2 * id[args[1]] + 1];
        }
    } else
        p -> eta = delay + d[2 * id[args[0]]][2 * id[args[0]] + 1];
    match_let.unlock();
    return p;
}

Std* at(std::string _id, float args[]) {
    auto p = stds[_id];
    heads[_id] -> front() -> lock = true;
    return p;
}

Std* done(std::string _id, float args[]) {
    osm_let.lock();
    match_let.lock();
    auto line = heads[_id];
    auto p = stds[_id], porter = line -> front();
    if (!p -> baby || p -> cross && p -> baby -> _id == line -> back() -> _id || !p -> cross && p -> _id == line -> back() -> _id) {
        line -> pop_back();
        stds.erase(_id);
        bag.push(id[_id]);
        id.erase(_id);
        if (p -> baby) {
            stds.erase(p -> baby -> _id);
            bag.push(id[p -> baby -> _id]);
            id.erase(p -> baby -> _id);
            delete p -> baby;
        }
        delete p;
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
//    show_me("done");
    osm_let.unlock();
    return p;
}

int main(int argc, const char *argv[]) {
    const rlim_t kStackSize = 128 * 1024 * 1024;
    struct rlimit rl;
    int result = getrlimit(RLIMIT_STACK, &rl);
    if (result == 0 && rl.rlim_cur < kStackSize) {
        rl.rlim_cur = kStackSize;
        result = setrlimit(RLIMIT_STACK, &rl);
        if (result != 0)
            fprintf(stderr, "setrlimit returned result = %d\n", result);
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
    config.storage_config = {argv[3]};
    config.use_shared_memory = false;
    config.algorithm = EngineConfig::Algorithm::CH;
    OSRM _osrm = OSRM(config);
    osm = &_osrm;

    std::thread(push_loop).detach();
    std::thread(imagination_loop).detach();
    std::thread(router_loop).detach();

    hang = argv[1];
    solver = argv[2];
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