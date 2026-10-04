#include <cstdint>
#include <cstdio>
extern "C" std::uint64_t report_observe(std::uint64_t, std::int64_t, bool, std::int64_t);
int main() {
    struct Item {std::uint64_t packed; std::int64_t width; std::uint64_t good; std::int64_t index;};
    Item in;
    while (std::fread(&in,sizeof(in),1,stdin)==1) {
        if (in.good>1) return 1;
        auto out=report_observe(in.packed,in.width,in.good!=0,in.index);
        if (std::fwrite(&out,sizeof(out),1,stdout)!=1) return 2;
    }
    return std::ferror(stdin)?3:0;
}
