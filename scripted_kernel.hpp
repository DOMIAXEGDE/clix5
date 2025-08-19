// scripted_kernel.hpp — Kernel + Plugin API (file-based; no scripted_exec.hpp)
// C++23, header-only. Place beside scripted_core.hpp.
#pragma once
#include "scripted_core.hpp"

#include <filesystem>
#include <fstream>
#include <sstream>
#include <cstdlib>
#include <iostream>
#include <vector>
#include <string>

namespace scripted {
namespace kernel {

using std::string;
namespace fs = std::filesystem;

// ---------- tiny helpers ----------
inline bool readTextFile(const fs::path& p, string& out) {
    std::ifstream in(p, std::ios::binary);
    if (!in) return false;
    out.assign((std::istreambuf_iterator<char>(in)), {});
    return true;
}
inline bool writeTextFile(const fs::path& p, const string& s) {
    fs::create_directories(p.parent_path());
    std::ofstream out(p, std::ios::binary | std::ios::trunc);
    if (!out) return false;
    out.write(s.data(), static_cast<std::streamsize>(s.size()));
    return static_cast<bool>(out);
}
inline std::string jsonEscape(const std::string& s) {
    std::string o; o.reserve(s.size() + 8);
    for (unsigned char c : s) {
        switch (c) {
            case '\\': o += "\\\\"; break;
            case '\"': o += "\\\""; break;
            case '\b': o += "\\b";  break;
            case '\f': o += "\\f";  break;
            case '\n': o += "\\n";  break;
            case '\r': o += "\\r";  break;
            case '\t': o += "\\t";  break;
            default:
                if (c < 0x20) { char buf[7]; std::snprintf(buf, sizeof(buf), "\\u%04X", c); o += buf; }
                else o += static_cast<char>(c);
        }
    }
    return o;
}

// ---------- manifest ----------
struct PluginManifest {
    string   name;
    string   entry_win; // e.g., "run.bat"
    string   entry_lin; // e.g., "run.sh"
    fs::path dir;
};

inline string jsonGetStr(const string& j, const string& key) {
    auto p = j.find("\"" + key + "\"");
    if (p == string::npos) return {};
    p = j.find(':', p);           if (p == string::npos) return {};
    p = j.find('"', p);           if (p == string::npos) return {};
    auto q = j.find('"', p + 1);  if (q == string::npos) return {};
    return j.substr(p + 1, q - (p + 1));
}

inline PluginManifest loadManifest(const fs::path& dir) {
    PluginManifest m; m.dir = dir;
    string j; (void)readTextFile(dir / "plugin.json", j);
    m.name      = jsonGetStr(j, "name");
    m.entry_win = jsonGetStr(j, "entry_win");
    m.entry_lin = jsonGetStr(j, "entry_lin");
    return m;
}

inline std::vector<PluginManifest> discoverPlugins(const fs::path& root = fs::path("plugins")) {
    std::vector<PluginManifest> out;
    if (!fs::exists(root)) return out;
    for (auto& e : fs::directory_iterator(root)) {
        if (!e.is_directory()) continue;
        auto dir = e.path();
        if (fs::exists(dir / "plugin.json")) {
            auto m = loadManifest(dir);
            if (!m.name.empty()) out.push_back(std::move(m));
        }
    }
    return out;
}

// ---------- Kernel ----------
struct Kernel {
    const Config& cfg;
    Workspace&    ws;
    Paths         paths;
    std::vector<PluginManifest> plugins;

    Kernel(const Config& c, Workspace& w) : cfg(c), ws(w) { plugins = discoverPlugins(); }
    void refresh() { plugins = discoverPlugins(); }

    void list() const {
        if (plugins.empty()) { std::cout << "(no plugins)\n"; return; }
        for (auto& p : plugins) std::cout << " - " << p.name << " @ " << p.dir.string() << "\n";
    }
    const PluginManifest* find(const string& name) const {
        for (auto& p : plugins) if (p.name == name) return &p;
        return nullptr;
    }

    // Runs plugin by name against bank/reg/addr.
    // stdin_json_or_path: either a path to a .json file or an inline JSON string (e.g., "{}").
    // Produces: files/out/plugins/<bank>/r<reg>a<addr>/<plugin>/{code.txt,input.json,output.json,run.log,run.err,run.cmd}
    bool run(const string& name, long long bank, long long reg, long long addr,
             const string& stdin_json_or_path,
             string& out_json, string& out_report)
    {
        auto P = find(name);
        if (!P) { out_report = "Plugin not found: " + name; return false; }

        // Ensure bank is loaded and resolve the code cell
        string err;
        (void)ensureBankLoadedInWorkspace(cfg, ws, bank, err);
        Resolver R(cfg, ws);

        string raw;
        if (!R.getValue(bank, reg, addr, raw)) {
            out_report = "No value at reg " + std::to_string(reg) + " addr " + std::to_string(addr);
            return false;
        }
        std::unordered_set<string> visited;
        string code = R.resolve(raw, bank, visited);

        // Layout
        string bankStr = string(1, cfg.prefix) + toBaseN(bank, cfg.base, cfg.widthBank);
        string regStr  = toBaseN(reg,  cfg.base, cfg.widthReg);
        string addrStr = toBaseN(addr, cfg.base, cfg.widthAddr);

        fs::path outdir = fs::path("files/out/plugins") / bankStr / ("r" + regStr + "a" + addrStr) / name;
        fs::create_directories(outdir);

        // Select entry and normalize paths
        const std::string entry = scripted::kWindows ? P->entry_win : P->entry_lin;
        if (entry.empty()) { out_report = "Plugin entry not set in manifest."; return false; }

        fs::path absOutdir  = fs::absolute(outdir);
        fs::path entryPath  = fs::absolute(P->dir / fs::path(entry));
        fs::path codeFile   = absOutdir / "code.txt";
        fs::path inputFile  = absOutdir / "input.json";
        fs::path outputFile = absOutdir / "output.json";
        fs::path logFile    = absOutdir / "run.log";
        fs::path errFile    = absOutdir / "run.err";

        if (!fs::exists(entryPath)) {
            out_report = "Entry not found: " + entryPath.string();
            return false;
        }

        if (!writeTextFile(codeFile, code)) {
            out_report = "Cannot write " + codeFile.string();
            return false;
        }

        string stdin_json = "{}";
        if (!stdin_json_or_path.empty()) {
            if (fs::exists(stdin_json_or_path)) (void)readTextFile(stdin_json_or_path, stdin_json);
            else stdin_json = stdin_json_or_path;
        }

        // Write input.json (JSON-escaped strings; stdin is inserted as-is)
        std::ostringstream is;
        is << "{\n";
        is << "  \"bank\": \""      << jsonEscape(bankStr)              << "\",\n";
        is << "  \"reg\": \""       << jsonEscape(regStr)               << "\",\n";
        is << "  \"addr\": \""      << jsonEscape(addrStr)              << "\",\n";
        is << "  \"title\": \""     << jsonEscape(ws.banks[bank].title) << "\",\n";
        is << "  \"code_file\": \"" << jsonEscape(codeFile.string())    << "\",\n";
        is << "  \"stdin\": "       << (stdin_json.empty() ? "{}" : stdin_json) << "\n";
        is << "}\n";
        if (!writeTextFile(inputFile, is.str())) {
            out_report = "Cannot write " + inputFile.string();
            return false;
        }

        // --- Build command and execute (Windows) ---
        int ec = 0;

        #ifdef _WIN32
            auto dq = [](const std::string& s){ return "\"" + s + "\""; };

            // Build the inner command with plain quotes
            const std::string inner =
                dq(entryPath.string()) + " " +
                dq(inputFile.string()) + " " +
                dq(absOutdir.string()) + " > " +
                dq(logFile.string())   + " 2> " +
                dq(errFile.string());

            // Wrap with ONE outer pair of quotes for /S /C
            const std::string cmd = std::string("cmd.exe /S /C ") + "\"" + inner + "\"";

            // Breadcrumb (so you can run it by hand)
            writeTextFile(absOutdir / "run.cmd", std::string("@echo off\r\n") + cmd + "\r\n");

            // Execute
            //int ec = std::system(cmd.c_str());
            ec = std::system(cmd.c_str());
        #else
            // --- POSIX branch unchanged (already fine) ---
            auto sq = [](const std::string& s){ return "'" + s + "'"; };
            const std::string inner =
                "\"" + entryPath.string() + "\" " +
                "\"" + inputFile.string() + "\" " +
                "\"" + absOutdir.string() + "\" > " +
                "\"" + logFile.string()   + "\" 2> " +
                "\"" + errFile.string()   + "\"";
            const std::string cmd = std::string("/bin/sh -c ") + sq(inner);
            ec = std::system(cmd.c_str());
        #endif

        // Read plugin output/report
        std::string outContent;
        if (!readTextFile(outputFile, outContent)) {
            std::string errtxt; (void)readTextFile(errFile, errtxt);
            out_report = "Plugin did not produce output.json. Exit=" + std::to_string(ec) +
                        (errtxt.empty() ? "" : ("\nerr:\n" + errtxt));
            return false;
        }
        out_json = std::move(outContent);

        std::string logtxt; (void)readTextFile(logFile, logtxt);
        std::string errtxt; (void)readTextFile(errFile, errtxt);
        std::ostringstream rep;
        rep << "exit=" << ec << "\n";
        if (!logtxt.empty()) rep << "log:\n" << logtxt << "\n";
        if (!errtxt.empty()) rep << "stderr:\n" << errtxt << "\n";
        out_report = rep.str();
        return true;

    }
};

} // namespace kernel
} // namespace scripted
