// Host for console_service.py's shared files policy fixture: copied snapshots and contracts.
#include <array>
#include <cstdint>
extern "C" long files_contract();
extern "C" long typed_files_contract();
extern "C" long append_contract();
extern "C" long copy_contract();
extern "C" long span_compare_contract();
extern "C" void checked_files_snapshot(long, void *);
int main() {
    if (const auto result = span_compare_contract())
        return 20 + int(result);
    if (const auto result = files_contract())
        return int(result);
    if (const auto result = typed_files_contract())
        return 40 + int(result);
    if (const auto result = append_contract())
        return 80 + int(result);
    if (const auto result = copy_contract())
        return 100 + int(result);
    for (long stage = 0; stage != 7; ++stage) {
        std::array<unsigned char, 280> storage{};
        storage.fill(0xa5);
        checked_files_snapshot(stage, storage.data() + 8);
        std::array<unsigned char, 264> expected{};
        if (stage > 0 && stage < 4) {
            expected[0] = 8;
            expected[1] = stage == 1 ? 49 : stage == 2 ? 1 : 0;
            for (unsigned i = 0; i != 8; ++i)
                expected[2 + i] = "abcdefgh"[i];
            for (unsigned i = 0; i != expected[1]; ++i)
                expected[10 + i] = stage == 1 ? 'x' : 'y';
            expected[256] = 1;
        }
        if (stage > 4) {
            expected[0] = 3;
            expected[1] = stage == 5 ? 1 : 0;
            for (unsigned i = 0; i != 3; ++i)
                expected[2 + i] = "src"[i];
            expected[64] = 4;
            expected[65] = expected[1];
            for (unsigned i = 0; i != 4; ++i)
                expected[66 + i] = "dest"[i];
            if (stage == 5) {
                expected[10] = 'x';
                expected[74] = 'x';
            }
            expected[256] = 3;
        }
        for (unsigned i = 0; i != storage.size(); ++i) {
            if (storage[i] != (i < 8 || i >= 272 ? 0xa5 : expected[i - 8]))
                return 10 + int(stage);
        }
    }
}
