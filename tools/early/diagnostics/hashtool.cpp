#include <cstdio>
#include <cstring>
#include <cstdint>
#include <string>
#include <iostream>
#include "rapidhash.h"
int main(){ std::ios::sync_with_stdio(false); std::string line;
  while(std::getline(std::cin,line)){ if(!line.empty() && line.back()=='\r') line.pop_back();
    uint64_t h=rapidhash(line.data(),line.size()); printf("%llx\n",(unsigned long long)h);} return 0; }
