#include <cstdint>
#include <cstdio>
extern "C" std::uint64_t review(std::uint64_t, std::int64_t, std::int64_t, bool);
int main() {
    struct Input {std::uint64_t packed;std::int64_t offset,count;std::uint64_t final;};
    Input item;
    while (std::fread(&item,sizeof(item),1,stdin)==1) {
        if (item.final>1) return 2;
        std::uint64_t result=review(item.packed,item.offset,item.count,item.final!=0);
        if (std::fwrite(&result,sizeof(result),1,stdout)!=1) return 3;
    }
    return std::ferror(stdin) ? 4 : 0;
}
