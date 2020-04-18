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
#include <string>
#include <utility>
#include <cstdlib>
#include <chrono>
#include <tsl/robin_map.h>
#include <tsl/robin_set.h>

#define MAX_N 2000

using namespace osrm;

struct Std {
    int a;
    std::string b;
//    std::string _id;
//    float s[2];
//    float t[2];
//    float _t[2];
//    int d;
//    int eta;
//    int prev;
//    int next;
//    int score;
};

tsl::robin_map<std::string, int> id;
tsl::robin_set<int> bag;

TableParameters *params = new TableParameters();
//std::unordered_map<std::string, int> id;

int d [2 * MAX_N][2 * MAX_N];


void rnd(float* r, float* s, float* t) {
    r[0] = ((float) rand()) / (float) RAND_MAX;
    r[1] = ((float) rand()) / (float) RAND_MAX;
    r[0] = (t[0] - s[0]) * r[0] + s[0];
    r[1] = (t[1] - s[1]) * r[1] + s[1];
}

int main(int argc, const char *argv[]) {
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0] << " data.osrm\n";
        return EXIT_FAILURE;
    }

    using namespace std::chrono;

    EngineConfig config;
    config.storage_config = {argv[1]};
    config.use_shared_memory = false;
    config.algorithm = EngineConfig::Algorithm::CH;
    const OSRM osrm{config};

    float s[2] = {35.611480, 51.138294};
    float t[2] = {35.816092, 51.590117};
    float r[2];

    Std *a = new Std{2, "ali"};
    std::cout << a -> a << std::endl;
    delete a;
    std::cout << a -> a << std::endl;

    int now = duration_cast< milliseconds >(
        system_clock::now().time_since_epoch()
    ).count() / 1000;

    for (int j = 0; j < 20; j++) {
        for (int i = 0; i < 6000; i++) {
            rnd(r, s, t);
            params -> coordinates.push_back({util::FloatLongitude{r[1]}, util::FloatLatitude{r[0]}});

            if (i < 20) params -> destinations.push_back(i);
            params -> sources.push_back(i);
        }
//        params.sources.push_back(1);
//        params.sources.push_back(2);
//        params.sources.push_back(3);
//        params.sources.push_back(4);
//        std::cout << params.sources.size() << '\n';

        json::Object result;
        const auto status = osrm.Table(*params, result);
        auto &durations = result.values["durations"].get<json::Array>().values;
        std::cout << durations.front().get<json::Array>().values.at(1).get<json::Number>().value << "\n";
        params = new TableParameters();
    }
    std::cout << duration_cast< milliseconds >(
        system_clock::now().time_since_epoch()
    ).count() / 1000 - now << '\n';
    return EXIT_SUCCESS;
}
