#include <iostream>
#include <string>
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

#include "lap.h"

typedef std::chrono::high_resolution_clock Clock;

#define MAX_N 2000

struct Std {
    std::string _id;
    float s[2];
    float t[2];
    float _t[2];
    int d;
    int eta;
    int prev;
    int next;
    int score;
    bool lock;
    bool cross;
    Std *baby;
};

tsl::robin_map<std::string, Std> stds;
tsl::robin_map<std::string, int> id;
std::stack<int> bag;
std::vector<Std> line;  // by default line filled with free porters

int d [2 * MAX_N][2 * MAX_N];

bool update_lock;
Clock::time_point update_time_point = Clock::now();
void _update(int milliseconds) {
    std::cout << "haa ha ha\n";
    if (update_lock) return;
    std::this_thread::sleep_for(std::chrono::milliseconds(milliseconds));
    update_lock = true;
    // do updating
    update_time_point = Clock::now();
    update_lock = false;
}

void call_from_thread(int tid) {
    std::this_thread::sleep_for(std::chrono::milliseconds(1000));
    std::cout << "Launched by thread " << tid << std::endl;
}

std::queue<Std> update_q;
void update_d(Std std) {
    update_q.push(std);
    int delay = 1000 * 5 * exp(-7 / 10 * sqrt(update_q.size()));
    Clock::time_point now = Clock::now();
    Clock::time_point _update_time_point = now + std::chrono::milliseconds(delay);
    if (update_time_point < now || _update_time_point < update_time_point) {
        update_time_point = _update_time_point;
        std::thread t = std::thread(_update, delay);
        t.detach();
    }
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
        std = { _id, {0, 0}, {lat, lng}, {0, 0}, d, 0, -1, -1, -1, false, false, nullptr };
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
    Std std = { _id, {slat, slng}, {tlat, tlng}, {0, 0}, d, 0, -1, -1, -1, false, false, nullptr };

    update_d(std);
}

void sell(std::string _id) { // no need for anything with topology we can find if it is batch and who is
    stds[_id].lock = true;
}

void at(std::string _id) {
    line[stds[_id].prev].cross = true;
}

void done(std::string _id) {
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
    /* tessil page

    for(auto it = map.begin(); it != map.end(); ++it) {
        //it->second = 2; // Illegal
        it.value() = 2; // Ok
    }
    */
}

void match(int undo, int redo) {
    // get heads from line .t
    // get all other ones .s
    // d, eta -> future edges
    // cost
    // lap
    // sort edges
    // while redo: add
}

int main() {
    /*
    match -> sort -> choose -> match*
        -> cost -> lap ->
    d changes -> undo(t) -> redo upper loop
    list have to update d[][] -> new path, free's location
    #2 on at and sell we can update eta
    open file containing mus then create cost <


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
*/
    int n_dim = 100;
    int verbose = 0;

    float cost [n_dim - 2][n_dim];

    for (int i = 0; i < n_dim - 2; i ++)
        for (int j = 0; j < n_dim; j++)
            cost [i][j] = ((float) rand()) / (float) RAND_MAX;

    int rowsol[n_dim - 2];
    int colsol[n_dim];

    float u[n_dim - 2];
    float v[n_dim];
    for (int i = 0; i < n_dim; i ++) {
        u[i] = .0;
        v[i] = .0;
    }

    auto cost_matrix = reinterpret_cast<float*>(cost);
    lap(n_dim, cost_matrix, verbose, rowsol, colsol, u, v);

    for (int i = 0; i < n_dim; i ++)
        std::cout << u[i] << ' ';
    auto _end = std::chrono::system_clock::now();

//    std::cout << rowsol[0] << ' ' << rowsol[1] << ' ' << rowsol[2] << '\n';
//    std::cout << colsol[0] << ' ' << colsol[1] << ' ' << colsol[2] << '\n';
//
//    std::cout << u[0] << ' ' << u[1] << ' ' << u[2] << '\n';
//    std::cout << v[0] << ' ' << v[1] << ' ' << v[2] << '\n';

    return EXIT_SUCCESS;
}

typedef Std (*FnPtr)(std::string, float []);
tsl::robin_map<std::string, FnPtr> methods;

#include <iostream>
#include <sstream>

int _main(int argc, char *argv[]) {
    for (int i = 0; i < MAX_N; i++)
        bag.push(i);
    methods["location"] = location;
    methods["insert"] = insert;
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
    while (true) {
        buff_size = recv(sock, buff, 1024, 0);
        for (buff_p = 0; buff_p < buff_size; buff_p ++) {
            if (buff[buff_p] == ',') {
                if (method == "") method = token;
                else if (_id == "") _id = token;
                else args[args_p ++] = std::stof(token);
                token = "";
                continue;
            }
            token += buff[buff_p];
        }
        methods[method](_id, args);
        args_p = 0;
        token = "";
        method = "";
        _id = "";
    }
    close(sock);
    unlink(NAME);
}