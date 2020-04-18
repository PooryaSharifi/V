#include <opencv2/opencv.hpp>
#include <sys/resource.h>
#include <iostream>
#include <vector>
//
//cv::Vec3b pixels[10000][10000];

int merge() {
    cv::Mat roads = cv::imread("/home/poorya/tehran_hhh.png", cv::IMREAD_UNCHANGED);
    cv::Mat satellite = cv::imread("/home/poorya/tehran_a.png", cv::IMREAD_UNCHANGED);
    // open both -> if distance is much  alpha is lower than 200 make them 0, 0, 0, 0

    for(int i = 0; i < roads.rows; i++) {
        for(int j = 0; j < roads.cols; j++) {
            cv::Vec4b & pixel  = roads.at<cv::Vec4b>(i, j);
            cv::Vec3b & cell = satellite.at<cv::Vec3b>(i, j);
            if (pixel[3] < 50) pixel[3] = 0;
            else if (
                (pixel[0] - cell[0]) * (pixel[0] - cell[0]) +
                (pixel[1] - cell[1]) * (pixel[1] - cell[1]) +
                (pixel[2] - cell[2]) * (pixel[2] - cell[2])
            > 2000) {
                pixel[0] = cell[0];
                pixel[1] = cell[1];
                pixel[2] = cell[2];
                pixel[3] = 0;
            }
        }
    }

    cv::imwrite("/home/poorya/tehran_a.png", roads);
}

std::vector <cv::Vec4b> list;
cv::Vec4b seeds[10];
std::vector <cv::Vec4b> clusters [10];

int distance(cv::Vec4b pixel, cv::Vec4b cell) {
    return (pixel[0] - cell[0]) * (pixel[0] - cell[0]) +
           (pixel[1] - cell[1]) * (pixel[1] - cell[1]) +
           (pixel[2] - cell[2]) * (pixel[2] - cell[2]);
}

void iterate(int num) {
    for (auto const &pixel : list) {
        clusters[0].push_back(pixel);
        int min = 0;
        for (int i = 1; i < num; i ++)
            if (distance(seeds[i], clusters[min].back()) < distance(seeds[min], clusters[min].back())) {
                clusters[i].push_back(clusters[min].back());
                clusters[min].pop_back();
                min = i;
            }
    }
    for (int i = 0; i < num; i ++) {
        int seed[4] = {0, 0, 0, 0};
        for (auto const &pixel : clusters[i])
            for (int j = 0; j < 4; j ++)
                seed[j] += pixel[j];
        for (int j = 0; j < 4; j ++)
            seeds[i][j] = clusters[i].size() ? (int) (seed[j] / clusters[i].size()) : 0;
        std::cout << seeds[i] << " " << clusters[i].size() << std::endl;
    }
}

void mean() {
    for (int i = 0; i < 4; i ++)
        for (int j = 0; j < 4; j ++)
            seeds[i][j] = list[i * 71][j];
    for (int k = 0; k < 21; k ++) {
        iterate(4);
        std::cout << std::endl;
    }
}

int main() {
    cv::Mat pixels = cv::imread("/home/poorya/tehran_aa.png", cv::IMREAD_UNCHANGED);
    int colors[3][3] = {
        {97, 215, 102},
        {253, 148, 74},
        {242, 58, 48}
    };
    for (int i = 0; i < 3; i ++)
        for (int j = 0; j < 3; j ++)
            seeds[i][j] = colors[i][2 - j];
    for (int i = 0; i < 3; i ++)
        std::cout << seeds[i] << std::endl;
    for(int i = 0; i < pixels.rows; i++)
        for(int j = 0; j < pixels.cols; j++) {
            cv::Vec4b & pixel = pixels.at<cv::Vec4b>(i, j);
            if (pixel[3]) {
                // list.push_back(pixel);
                auto min = 0;
                for (int k = 0; k < 3; k ++)
                    if (distance(seeds[k], pixel) < distance(seeds[min], pixel))
                        min = k;
                for (int k = 0; k < 3; k ++)
                    pixel[k] = seeds[min][k];
            }
        }
    cv::imwrite("/home/poorya/tehran_z.png", pixels);
}