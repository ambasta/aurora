// Host for console_service.py's shared note policy fixture.
extern "C" long note_contract();
int main() {
    return int(note_contract());
}
