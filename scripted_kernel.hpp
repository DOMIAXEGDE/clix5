// scripted_kernel.hpp — Kernel + Plugin API (file-based; no scripted_exec.hpp)
// C++23, header-only. Place beside scripted_core.hpp.
#pragma once
#include "scripted_core.hpp"
#include <iostream>
#include <fstream>

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
            out.write(s.data(), (std::streamsize)s.size());
            return (bool)out;
        }
        inline string quote(const string& s) { return "\"" + s + "\""; }

        // ---------- manifest ----------
        struct PluginManifest {
            string name;
            string entry_win; // e.g., "run.bat"
            string entry_lin; // e.g., "run.sh"
            fs::path dir;
        };

        inline string jsonGetStr(const string& j, const string& key) {
            auto p = j.find("\"" + key + "\"");
            if (p == string::npos) return {};
            p = j.find(':', p); if (p == string::npos) return {};
            p = j.find('"', p); if (p == string::npos) return {};
            auto q = j.find('"', p + 1); if (q == string::npos) return {};
            return j.substr(p + 1, q - (p + 1));
        }

        inline PluginManifest loadManifest(const fs::path& dir) {
            PluginManifest m; m.dir = dir;
            string j; (void)readTextFile(dir / "plugin.json", j);
            m.name = jsonGetStr(j, "name");
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
            Workspace& ws;
            Paths paths;
            std::vector<PluginManifest> plugins;

            Kernel(const Config& c, Workspace& w) : cfg(c), ws(w) { plugins = discoverPlugins(); }
            void refresh() { plugins = discoverPlugins(); }

            void list() const {
                if (plugins.empty()) { std::cout << "(no plugins)\n"; return; }
                for (auto& p : plugins) {
                    std::cout << " - " << p.name << " @ " << p.dir.string() << "\n";
                }
            }
            const PluginManifest* find(const string& name) const {
                for (auto& p : plugins) if (p.name == name) return &p;
                return nullptr;
            }

            // Runs plugin by name against current bank/reg/addr.
            // stdin_json_or_path: either a path to a .json file or an inline JSON string (e.g., "{}").
            // Produces files/out/plugins/<bank>/r<reg>a<addr>/<plugin>/{code.txt,input.json,output.json,run.log,run.err}
            bool run(const string& name, long long bank, long long reg, long long addr,
                const string& stdin_json_or_path,
                string& out_json, string& out_report)
            {
                auto P = find(name);
                if (!P) { out_report = "Plugin not found: " + name; return false; }

                // Ensure bank loaded and resolve code
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
                string regStr = toBaseN(reg, cfg.base, cfg.widthReg);
                string addrStr = toBaseN(addr, cfg.base, cfg.widthAddr);
                fs::path outdir = fs::path("files/out/plugins") / bankStr / ("r" + regStr + "a" + addrStr) / name;
                fs::create_directories(outdir);

                fs::path codeFile = outdir / "code.txt";
                fs::path inputFile = outdir / "input.json";
                fs::path outputFile = outdir / "output.json";
                fs::path logFile = outdir / "run.log";
                fs::path errFile = outdir / "run.err";

                if (!writeTextFile(codeFile, code)) { out_report = "Cannot write " + codeFile.string(); return false; }

                string stdin_json = "{}";
                if (!stdin_json_or_path.empty()) {
                    if (fs::exists(stdin_json_or_path)) (void)readTextFile(stdin_json_or_path, stdin_json);
                    else stdin_json = stdin_json_or_path;
                }

                std::ostringstream is;
                is << "{\n";
                is << "  \"bank\": \"" << bankStr << "\",\n";
                is << "  \"reg\": \"" << regStr << "\",\n";
                is << "  \"addr\": \"" << addrStr << "\",\n";
                is << "  \"title\": \"" << ws.banks[bank].title << "\",\n";
                is << "  \"code_file\": \"" << codeFile.string() << "\",\n";
                is << "  \"stdin\": " << (stdin_json.empty() ? "{}" : stdin_json) << "\n";
                is << "}\n";
                if (!writeTextFile(inputFile, is.str())) { out_report = "Cannot write " + inputFile.string(); return false; }

                // Entry script selection
                string entry = scripted::kWindows ? P->entry_win : P->entry_lin;
                fs::path entryPath = P->dir / entry;
                if (!fs::exists(entryPath)) { out_report = "Entry not found: " + entryPath.string(); return false; }

                // Build command (redirect stdout/stderr to files)
                std::ostringstream cmd;
                if (scripted::kWindows) {
                    cmd << "cmd /C " << quote(entryPath.string()) << " " << quote(inputFile.string()) << " " << quote(outdir.string())
                        << " >" << quote(logFile.string()) << " 2>" << quote(errFile.string());
                }
                else {
                    cmd << "/bin/sh -c " << quote(quote(entryPath.string()) + " " + quote(inputFile.string()) + " " + quote(outdir.string())
                        + " >" + quote(logFile.string()) + " 2>" + quote(errFile.string()));
                }
                int ec = std::system(cmd.str().c_str());

                string outj;
                if (!readTextFile(outputFile, outj)) {
                    string errtxt; (void)readTextFile(errFile, errtxt);
                    out_report = "Plugin did not produce output.json. Exit=" + std::to_string(ec) +
                        (errtxt.empty() ? "" : ("\nerr:\n" + errtxt));
                    return false;
                }
                out_json = outj;

                string logtxt; (void)readTextFile(logFile, logtxt);
                string errtxt; (void)readTextFile(errFile, errtxt);
                std::ostringstream rep;
                rep << "exit=" << ec << "\n";
                if (!logtxt.empty()) rep << "log:\n" << logtxt << "\n";
                if (!errtxt.empty()) rep << "stderr:\n" << errtxt << "\n";
                out_report = rep.str();
                return true;
            }
        };

    }
} // namespace scripted::kernel
