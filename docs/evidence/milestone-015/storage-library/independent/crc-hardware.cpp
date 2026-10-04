#include <cstdint>
#include <iostream>
#include <vector>
#include <nmmintrin.h>
__attribute__((target("sse4.2"))) std::uint32_t checksum(std::uint32_t previous,const std::vector<unsigned char>& b){auto c=previous^0xffffffffU;for(auto x:b)c=_mm_crc32_u8(c,x);return c^0xffffffffU;}
int main(){if(!__builtin_cpu_supports("sse4.2")){std::cerr<<"SSE4.2 unavailable\n";return 77;}std::uint64_t prior,n,x;while(std::cin>>prior>>n){if(prior>0xffffffffU||n>4096)return 2;std::vector<unsigned char>b;for(std::uint64_t i=0;i<n;++i){if(!(std::cin>>x)||x>255)return 3;b.push_back(x);}std::cout<<checksum(prior,b)<<'\n';}}
