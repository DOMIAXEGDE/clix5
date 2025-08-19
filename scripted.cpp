// scripted.cpp — CLI REPL using shared core + new plugin Kernel
// g++ -std=c++23 -O2 scripted.cpp -o scripted.exe
#include <iostream>
#include <memory>
#include "scripted_core.hpp"
#include "scripted_kernel.hpp" // NEW

using namespace scripted;
using std::string;

struct Editor {
    Paths P;
    Config cfg;
    Workspace ws;
    std::unique_ptr<scripted::kernel::Kernel> K; // NEW
    std::optional<long long> current;
    bool dirty = false;

    void loadConfig() { cfg = ::scripted::loadConfig(P); K = std::make_unique<scripted::kernel::Kernel>(cfg, ws); }  // NEW
    void saveCfg() { saveConfig(P, cfg); }
    bool ensureCurrent() { if (!current) { std::cout << "No current context. Use :open <ctx>\n"; return false; } return true; }

void help(){
    std::cout <<
R"(────────────────────────────────────────────────────────────────────────────
scripted — Help / User Manual
────────────────────────────────────────────────────────────────────────────
Quick start
  :open x00001                Create or open context x00001
  :ins 0001 hello             Write to register 1, address 0001
  :insr 02 0003 world         Write to register 2, address 0003
  :show                       View current buffer
  :w                          Save to files/x00001.txt
  :resolve                    Write files/out/x00001.resolved.txt
  :export                     Write files/out/x00001.json
  :plugins                    List discovered code plugins
  :plugin_run python 02 0003 {}  Run plugin over reg 02 addr 0003
  :q                          Quit

Commands
  :help                          Show this help
  :open <ctx>                    Open/create context (e.g., x00001)
  :switch <ctx>                  Switch current context (loads if needed)
  :preload                       Load all banks in files/
  :ls                            List loaded contexts
  :show                          Print current buffer (header + addresses)
  :ins <addr> <value...>         Insert/replace into register 1
  :insr <reg> <addr> <value...>  Insert/replace into a specific register
  :del <addr>                    Delete from register 1
  :delr <reg> <addr>             Delete from a specific register
  :w                             Write current buffer to files/<ctx>.txt
  :r <path>                      Read/merge a bank file (same grammar as below)
  :resolve                       Write files/out/<ctx>.resolved.txt
  :export                        Write files/out/<ctx>.json
  :set prefix <char>             Set context prefix (default: x)
  :set base <n>                  Set number base (10/16/…); affects parse & show
  :set widths bank=5 addr=4 reg=2  Set zero-pad widths
  :plugins                       List discovered code plugins
  :plugin_run <name> <reg> <addr> [stdin.json|inlineJSON]
                                Run a plugin on the selected cell
  :q                             Quit (prompts if dirty)

Context file format (what :w writes, what :open/:r read)
  Header + body in braces:
    x00001 (demo context){
        0001    Hello from R1
    02
        0003    World from R2
    }
  Rules:
    • First line: <prefix><bankId> (title){
      - Example:  x00001 (demo context){
      - Title is optional; braces are required.
    • Body lines:
      - A line WITHOUT leading space/tab begins a register block: e.g. "02"
      - Indented lines (TAB or SPACE) are address/value entries:
            <indent><addr><whitespace><value...>
      - By default, entries go to register 1 until a register line appears.
    • Encoding: UTF-8 (BOM optional; loader strips BOM).
    • Indentation: TAB or SPACE are both accepted for address lines.

Resolver syntax (inside values)
  You can reference other cells; resolution is recursive with cycle checks.
  Forms supported:
    1) Numeric triad (bank.register.address) — any register:
         1.2.3
    2) Prefixed three-part (base-aware; uses current cfg.prefix):
         x00001.02.0003
    3) Same-bank shorthand (uses current bank; base-aware):
         r02.0003
    4) Two-part prefixed (bank.address) — always register 1:
         x00001.0001
  Missing targets show as: [Missing …]
  Bad references show as: [BadRef …]
  Circular refs show as:  [Circular Ref: …]

Numbers, base, widths
  • :set base N     — parsing of <reg> and <addr> follows the current base.
  • :set widths …   — affects how :show and filenames zero-pad the ids.
  • You can enter “02” in base 10 or “0A” in base 16, depending on :set base.

Plugins (file-based, language-agnostic)
  Discovery:
    plugins/*/plugin.json with:
      { "name": "<pluginName>", "entry_win": "run.bat", "entry_lin": "run.sh" }
  Invocation:
    :plugin_run <name> <reg> <addr> [stdin.json|inlineJSON]
  Kernel writes for each run:
    files/out/plugins/<ctx>/r<reg>a<addr>/<plugin>/
      code.txt       — resolved value of the cell
      input.json     — metadata + optional stdin object
      output.json    — REQUIRED plugin result (written by the plugin)
      run.log / run.err
  Note: The working directory is the program’s CWD; place plugins/ at repo root
        (or as staged by your build script) so Kernel discovery finds them.

Typical session
  :open x00001
  :ins 0001 Hello
  :insr 02 0003 World
  :ins 0002 See r02.0003               # cross-register reference
  :show
  :w
  :resolve
  :export
  :plugins
  :plugin_run python 02 0003 {"note":"demo"}

Troubleshooting
  • “Parse failed: cannot parse bank id”
      - File begins with a BOM or wrong header. Ensure first line is like:
        x00001 (title){
      - Our loader strips UTF-8 BOM; if hand-editing, save as UTF-8.
  • “missing '{' after header”
      - Header must be followed by “{” (on the same line or next line).
  • “invalid register line: …”
      - Address lines must be indented (TAB or SPACE). Non-indented lines
        are treated as register ids (e.g. “02”).
  • Values don’t resolve
      - Use 1.2.3 or x00001.02.0003 (or r02.0003). x00001.0003 targets reg 1.
      - Check :set base — your hex vs decimal digits must match.

Paths & outputs
  Input banks:      files/<ctx>.txt
  Resolved text:    files/out/<ctx>.resolved.txt
  Exported JSON:    files/out/<ctx>.json
  Plugin outputs:   files/out/plugins/<ctx>/r<reg>a<addr>/<plugin>/output.json

────────────────────────────────────────────────────────────────────────────
)" << std::endl;
}


    void listCtx() {
        if (ws.banks.empty()) { std::cout << "(no contexts)\n"; return; }
        for (auto& [id, b] : ws.banks) {
            std::cout << cfg.prefix << toBaseN(id, cfg.base, cfg.widthBank) << "  (" << b.title << ")"
                << (current && *current == id ? " [current]" : "") << "\n";
        }
    }

    void show() {
        if (!ensureCurrent()) return;
        std::cout << writeBankText(ws.banks[*current], cfg);
    }

    void write() {
        if (!ensureCurrent()) return;
        string err;
        if (!saveContextFile(cfg, contextFileName(cfg, *current), ws.banks[*current], err))
            std::cout << "Write failed: " << err << "\n";
        else { dirty = false; std::cout << "Saved " << contextFileName(cfg, *current).string() << "\n"; }
    }

    void insert(const string& addrTok, const string& value) {
        if (!ensureCurrent()) return;
        long long addr;
        if (!parseIntBase(addrTok, cfg.base, addr)) { std::cout << "Bad address\n"; return; }
        ws.banks[*current].regs[1][addr] = value; dirty = true;
    }

    void insertR(const string& regTok, const string& addrTok, const string& value) {
        if (!ensureCurrent()) return;
        long long reg = 1, addr = 0;
        if (!parseIntBase(regTok, cfg.base, reg)) { std::cout << "Bad register\n"; return; }
        if (!parseIntBase(addrTok, cfg.base, addr)) { std::cout << "Bad address\n";  return; }
        ws.banks[*current].regs[reg][addr] = value; dirty = true;
    }

    void del(const string& addrTok) {
        if (!ensureCurrent()) return;
        long long addr; if (!parseIntBase(addrTok, cfg.base, addr)) { std::cout << "Bad address\n"; return; }
        auto& m = ws.banks[*current].regs[1];
        size_t n = m.erase(addr);
        std::cout << (n ? "Deleted.\n" : "No such address.\n");
        if (n) dirty = true;
    }

    void delR(const string& regTok, const string& addrTok) {
        if (!ensureCurrent()) return;
        long long reg = 1, addr = 0;
        if (!parseIntBase(regTok, cfg.base, reg)) { std::cout << "Bad register\n"; return; }
        if (!parseIntBase(addrTok, cfg.base, addr)) { std::cout << "Bad address\n";  return; }
        auto& regs = ws.banks[*current].regs;
        auto itR = regs.find(reg);
        if (itR == regs.end()) { std::cout << "No such register.\n"; return; }
        size_t n = itR->second.erase(addr);
        std::cout << (n ? "Deleted.\n" : "No such address.\n");
        if (n) dirty = true;
        if (itR->second.empty()) regs.erase(itR);
    }

    void readMerge(const string& path) {
        if (!ensureCurrent()) return;
        std::ifstream in(path, std::ios::binary);
        if (!in) { std::cout << "Cannot open " << path << "\n"; return; }
        string text((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
        Bank tmp;
        auto pr = parseBankText(text, cfg, tmp);
        if (!pr.ok) { std::cout << "Parse failed: " << pr.err << "\n"; return; }
        for (auto& [rid, addrs] : tmp.regs)
            for (auto& [aid, val] : addrs)
                ws.banks[*current].regs[rid][aid] = val;
        if (ws.banks[*current].title.empty()) ws.banks[*current].title = tmp.title;
        dirty = true; std::cout << "Merged.\n";
    }

    void resolveOut() {
        if (!ensureCurrent()) return;
        auto txt = resolveBankToText(cfg, ws, *current);
        auto outp = outResolvedName(cfg, *current);
        std::ofstream out(outp, std::ios::binary); out << txt;
        std::cout << "Wrote " << outp << "\n";
    }

    void exportJson() {
        if (!ensureCurrent()) return;
        auto js = exportBankToJSON(cfg, ws, *current);
        auto outp = outJsonName(cfg, *current);
        std::ofstream out(outp, std::ios::binary); out << js;
        std::cout << "Wrote " << outp << "\n";
    }

    void repl() {
        P.ensure();
        loadConfig();
        std::cout << "scripted CLI — shared core\nType :help for commands.\n\n";
        std::cout << "scripted CLI — " << scripted::platformName() << (scripted::isWSL() ? " (WSL)" : "") << "\n";
        string line;
        while (true) {
            std::cout << ">> ";
            if (!std::getline(std::cin, line)) break;
            string s = trim(line);
            if (s.empty()) continue;

            if (s == ":help") { help(); continue; }
            if (s == ":ls") { listCtx(); continue; }
            if (s == ":show") { show(); continue; }
            if (s == ":w") { write(); continue; }
            if (s == ":preload") { preloadAll(cfg, ws); std::cout << "Preloaded " << ws.banks.size() << " banks.\n"; continue; }
            if (s == ":resolve") { resolveOut(); continue; }
            if (s == ":export") { exportJson(); continue; }
            if (s == ":plugins") { K->refresh(); K->list(); continue; }
            if (s == ":q") {
                if (dirty) {
                    std::cout << "Unsaved changes. Type :w to save or :q again to quit.\n>> ";
                    string l2; if (!std::getline(std::cin, l2)) break;
                    if (trim(l2) == ":q") break; else { s = trim(l2); }
                }
                else break;
            }

            // tokenized commands
            std::istringstream is(s); std::vector<string> tok;
            for (string t; is >> t;) tok.push_back(t);
            if (tok.empty()) continue;

            if (tok[0] == ":open" && tok.size() >= 2) {
                string status; if (openCtx(cfg, ws, tok[1], status)) {
                    string token = (tok[1][0] == cfg.prefix) ? tok[1].substr(1) : tok[1];
                    long long id; parseIntBase(token, cfg.base, id);
                    current = id;
                }
                std::cout << status << "\n"; continue;
            }

            if (tok[0] == ":switch" && tok.size() >= 2) {
                string name = tok[1]; if (name.size() > 4 && name.ends_with(".txt")) name = name.substr(0, name.size() - 4);
                string token = (name[0] == cfg.prefix) ? name.substr(1) : name;
                long long id; if (!parseIntBase(token, cfg.base, id)) { std::cout << "Bad id\n"; continue; }
                if (!ws.banks.count(id)) {
                    string status; if (!openCtx(cfg, ws, name, status)) { std::cout << status << "\n"; continue; }
                }
                current = id; std::cout << "Switched to " << name << "\n"; continue;
            }

            if (tok[0] == ":ins" && tok.size() >= 3) {
                string value; for (size_t i = 2; i < tok.size(); ++i) { if (i > 2) value.push_back(' '); value += tok[i]; }
                insert(tok[1], value); continue;
            }
            if (tok[0] == ":insr" && tok.size() >= 4) {
                string value; for (size_t i = 3; i < tok.size(); ++i) { if (i > 3) value.push_back(' '); value += tok[i]; }
                insertR(tok[1], tok[2], value); continue;
            }
            if (tok[0] == ":del" && tok.size() >= 2) { del(tok[1]); continue; }
            if (tok[0] == ":delr" && tok.size() >= 3) { delR(tok[1], tok[2]); continue; }
            if (tok[0] == ":r" && tok.size() >= 2) { readMerge(tok[1]); continue; }

            // NEW: plugin run
            if (tok[0] == ":plugin_run" && tok.size() >= 4) {
                if (!ensureCurrent()) { std::cout << "Open a context first\n"; continue; }
                long long r = 0, a = 0;
                if (!parseIntBase(tok[2], cfg.base, r) || !parseIntBase(tok[3], cfg.base, a)) { std::cout << "Bad reg/addr\n"; continue; }
                string stdinArg = (tok.size() >= 5 ? tok[4] : string("{}"));
                string out_json, report;
                bool ok = K->run(tok[1], *current, r, a, stdinArg, out_json, report);
                if (!ok) std::cout << "ERROR: " << report << "\n";
                else {
                    std::cout << "output.json:\n" << out_json << "\n";
                    if (!report.empty()) std::cout << report;
                }
                continue;
            }

            std::cout << "Unknown command. :help\n";
        }
        std::cout << "bye.\n";
    }
};

int main() {
    Editor ed;
    ed.repl();
    return 0;
}
