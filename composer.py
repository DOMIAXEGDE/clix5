#!/usr/bin/env python3
# composer.py — Universal Runtime GUI (Python 3.13, stdlib only)
# Single-run AND Pipeline chaining. No external dependencies.
# Works with .py/.exe/.bat/.cmd/.ps1 by discovering flags from --help.

import os, sys, re, json, shlex, subprocess, threading, time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_NAME = "Composer — Universal Runtime GUI"
PROFILE_FILE = Path.cwd() / "composer_profiles.json"
PIPELINE_FILE = Path.cwd() / "composer_pipelines.json"

HELP_FLAG_CANDIDATES = ["--help", "-h", "-?", "/?", "help"]
ARG_HINT_RE = re.compile(r"(FILE|PATH|DIR|NAME|INT|FLOAT|NUM|SIZE|PORT|MODEL|TOKEN|COUNT|JSON|OUT|INPUT|OUTPUT|SECONDS|MINUTES|HOURS)", re.I)
FLAG_RE = re.compile(r"(?x)(^\s*)(-\w|--[\w\-]+)(?P<tail>.*)")

# -------------- Launch helpers --------------

def guess_invocation(path: Path):
    ext = path.suffix.lower()
    if ext == ".py":
        return [sys.executable, str(path)]
    if ext in {".bat", ".cmd"} and os.name == "nt":
        return ["cmd", "/S", "/C", str(path)]
    if ext == ".ps1":
        shell = "pwsh" if shutil.which("pwsh") else ("powershell" if os.name=="nt" else "pwsh")
        return [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)]
    return [str(path)]

try:
    import shutil  # used in guess_invocation
except Exception:
    shutil = None

def run_help_capture(path: Path, workdir: Path|None=None):
    help_text = ""
    for flag in HELP_FLAG_CANDIDATES:
        try:
            cmd = guess_invocation(path) + [flag]
            proc = subprocess.run(cmd, cwd=workdir or path.parent, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=6)
            if proc.stdout:
                help_text = proc.stdout
                break
        except Exception:
            continue
    return help_text


def parse_options_from_help(help_text: str):
    options = []
    for ln in help_text.splitlines():
        m = FLAG_RE.search(ln)
        if not m:
            continue
        name = m.group(2).strip()
        tail = m.group('tail') or ''
        expects = bool(re.search(r"[\s=]<[\w\-]+>|\[[A-Z]+\]|=|" + ARG_HINT_RE.pattern, tail, re.I))
        options.append((name, expects, ln.strip()))
    # stable order: long first
    options.sort(key=lambda t: (0 if t[0].startswith("--") else 1, t[0]))
    return options

# -------------- Live Runner --------------
class LiveRunner:
    def __init__(self, cmd, cwd=None, env=None, on_stdout=None, on_stderr=None, on_done=None):
        self.cmd = cmd; self.cwd=cwd; self.env=env
        self.on_stdout=on_stdout; self.on_stderr=on_stderr; self.on_done=on_done
        self.proc=None
    def start(self):
        def target():
            try:
                self.proc = subprocess.Popen(self.cmd, cwd=self.cwd, env=self.env,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, bufsize=1, universal_newlines=True)
            except Exception as e:
                if self.on_stderr: self.on_stderr(str(e)+"\n")
                if self.on_done: self.on_done(-1)
                return
            def reader(stream, cb):
                try:
                    for line in iter(stream.readline, ""):
                        if cb: cb(line)
                finally:
                    try: stream.close()
                    except Exception: pass
            threading.Thread(target=reader, args=(self.proc.stdout, self.on_stdout), daemon=True).start()
            threading.Thread(target=reader, args=(self.proc.stderr, self.on_stderr), daemon=True).start()
            rc=self.proc.wait()
            if self.on_done: self.on_done(rc)
        threading.Thread(target=target, daemon=True).start()
    def terminate(self):
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
        except Exception:
            pass

# -------------- GUI --------------
class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.master.title(APP_NAME)
        self.master.geometry("1180x780")
        self.pack(fill="both", expand=True)

        # shared state
        self.program_path = tk.StringVar()
        self.workdir = tk.StringVar(value=str(Path.cwd()))
        self.positionals = tk.StringVar()
        self.env_lines = tk.StringVar(value="")
        self._opts_widgets = []
        self.current_runner=None
        self.last_output_file=None

        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True)
        self.single_frame = ttk.Frame(nb); nb.add(self.single_frame, text="Single Run")
        self.pipe_frame = ttk.Frame(nb); nb.add(self.pipe_frame, text="Pipeline")

        self._build_single()
        self._build_pipeline()

    # ---------- Single Run Tab ----------
    def _build_single(self):
        f = self.single_frame
        f.columnconfigure(1, weight=1)
        # program row
        row = ttk.Frame(f, padding=8); row.grid(row=0, column=0, columnspan=2, sticky="ew")
        row.columnconfigure(1, weight=1)
        ttk.Label(row, text="Program:").grid(row=0, column=0, sticky="w")
        ttk.Entry(row, textvariable=self.program_path).grid(row=0, column=1, sticky="ew")
        ttk.Button(row, text="Browse…", command=self._pick_program).grid(row=0, column=2, padx=6)
        ttk.Button(row, text="Help ↻", command=self._refresh_help).grid(row=0, column=3)

        # options
        self.opts_container = ttk.LabelFrame(f, text="Options (auto-discovered)")
        self.opts_container.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=8, pady=4)
        self.opts_container.columnconfigure(1, weight=1)

        bot = ttk.Frame(f, padding=8); bot.grid(row=2, column=0, columnspan=2, sticky="ew")
        bot.columnconfigure(1, weight=1)
        ttk.Label(bot, text="Positionals:").grid(row=0, column=0, sticky="w")
        ttk.Entry(bot, textvariable=self.positionals).grid(row=0, column=1, sticky="ew")
        ttk.Label(bot, text="Working dir:").grid(row=1, column=0, sticky="w")
        r = ttk.Frame(bot); r.grid(row=1, column=1, sticky="ew"); r.columnconfigure(0, weight=1)
        ttk.Entry(r, textvariable=self.workdir).grid(row=0, column=0, sticky="ew")
        ttk.Button(r, text="…", command=self._pick_workdir, width=3).grid(row=0, column=1, padx=4)
        ttk.Label(bot, text="Environment (KEY=VALUE per line)").grid(row=2, column=0, sticky="w", pady=(8,0))
        ttk.Entry(bot, textvariable=self.env_lines).grid(row=2, column=1, sticky="ew")

        runbar = ttk.Frame(f, padding=(8,4)); runbar.grid(row=3, column=0, columnspan=2, sticky="ew")
        runbar.columnconfigure(1, weight=1)
        self.run_btn = ttk.Button(runbar, text="▶ Run", command=self._run_clicked); self.run_btn.grid(row=0, column=0)
        self.cmd_preview = ttk.Entry(runbar); self.cmd_preview.grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(runbar, text="⎘ Copy", command=self._copy_cmd).grid(row=0, column=2)

        out = ttk.Frame(f); out.grid(row=4, column=0, columnspan=2, sticky="nsew"); f.rowconfigure(4, weight=1)
        out.columnconfigure(0, weight=1)
        self.output = tk.Text(out, wrap="word", bg="#0b1017", fg="#e5e7eb", insertbackground="#e5e7eb")
        self.output.grid(row=0, column=0, sticky="nsew")
        self.output.tag_configure("stderr", foreground="#ff6b6b")
        self.output.tag_configure("stdout", foreground="#a3e635")
        sb = ttk.Scrollbar(out, orient="vertical", command=self.output.yview); sb.grid(row=0, column=1, sticky="ns")
        self.output.configure(yscrollcommand=sb.set)

    # ---------- Pipeline Tab ----------
    def _build_pipeline(self):
        f = self.pipe_frame
        f.columnconfigure(1, weight=1); f.rowconfigure(2, weight=1)
        top = ttk.Frame(f, padding=8); top.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(top, text="Pipelines let you chain steps. Use {prev} token to inject prior output path.").pack(side="left")
        mid = ttk.Frame(f, padding=8); mid.grid(row=1, column=0, columnspan=2, sticky="ew")
        ttk.Button(mid, text="New Step", command=self._pipe_add).pack(side="left")
        ttk.Button(mid, text="Edit", command=self._pipe_edit).pack(side="left", padx=6)
        ttk.Button(mid, text="Remove", command=self._pipe_remove).pack(side="left")
        ttk.Button(mid, text="Up", command=lambda: self._pipe_move(-1)).pack(side="left", padx=6)
        ttk.Button(mid, text="Down", command=lambda: self._pipe_move(1)).pack(side="left")
        ttk.Button(mid, text="Save Pipeline", command=self._pipe_save).pack(side="left", padx=12)
        ttk.Button(mid, text="Load Pipeline", command=self._pipe_load).pack(side="left")

        body = ttk.Frame(f, padding=8); body.grid(row=2, column=0, columnspan=2, sticky="nsew")
        body.columnconfigure(0, weight=1)
        self.steps_lb = tk.Listbox(body, height=12); self.steps_lb.grid(row=0, column=0, sticky="nsew")

        run = ttk.Frame(f, padding=8); run.grid(row=3, column=0, columnspan=2, sticky="ew")
        self.pipe_btn = ttk.Button(run, text="▶ Run Pipeline", command=self._run_pipeline); self.pipe_btn.pack(side="left")

        out = ttk.Frame(f); out.grid(row=4, column=0, columnspan=2, sticky="nsew"); f.rowconfigure(4, weight=1)
        out.columnconfigure(0, weight=1)
        self.pipe_output = tk.Text(out, wrap="word", bg="#0b1017", fg="#e5e7eb", insertbackground="#e5e7eb")
        self.pipe_output.grid(row=0, column=0, sticky="nsew")
        self.pipe_output.tag_configure("stderr", foreground="#ff6b6b")
        self.pipe_output.tag_configure("stdout", foreground="#a3e635")
        sb = ttk.Scrollbar(out, orient="vertical", command=self.pipe_output.yview); sb.grid(row=0, column=1, sticky="ns")
        self.pipe_output.configure(yscrollcommand=sb.set)

        self.steps = []  # list of dicts: {program, args, workdir, env, capture_regex}

    # ---------- UI helpers ----------
    def _pick_program(self):
        path = filedialog.askopenfilename()
        if path:
            self.program_path.set(path)

    def _pick_workdir(self):
        d = filedialog.askdirectory(initialdir=self.workdir.get())
        if d:
            self.workdir.set(d)

    # ---------- Options discovery ----------
    def _refresh_help(self):
        for c in self.opts_container.winfo_children(): c.destroy()
        self._opts_widgets.clear()
        p = Path(self.program_path.get())
        if not p.exists():
            self._log(self.output, f"Program not found: {p}\n", err=True); return
        txt = run_help_capture(p, Path(self.workdir.get()) if self.workdir.get() else None)
        opts = parse_options_from_help(txt)
        if not opts:
            ttk.Label(self.opts_container, text="(No options discovered — use Positionals)").grid(row=0, column=0, sticky="w")
        else:
            for r,(name,expects,hlp) in enumerate(opts):
                var_en=tk.BooleanVar(); var_val=tk.StringVar()
                ttk.Checkbutton(self.opts_container,text=name,variable=var_en,command=self._update_cmd_preview).grid(row=r,column=0,sticky="w")
                if expects:
                    ttk.Entry(self.opts_container,textvariable=var_val).grid(row=r,column=1,sticky="ew")
                ttk.Label(self.opts_container,text=hlp,foreground="#9aa6b2").grid(row=r,column=2,sticky="w")
                self._opts_widgets.append((var_en,var_val,name,expects))
        self._update_cmd_preview()

    def _assemble_cmd(self):
        p = Path(self.program_path.get())
        cmd = guess_invocation(p)
        for var_en, var_val, name, expects in self._opts_widgets:
            if var_en.get():
                cmd.append(name)
                if expects and var_val.get().strip():
                    cmd.append(var_val.get().strip())
        pos = shlex.split(self.positionals.get())
        cmd.extend(pos)
        return cmd

    def _update_cmd_preview(self):
        cmd = self._assemble_cmd()
        disp = " ".join(shlex.quote(x) for x in cmd)
        self.cmd_preview.delete(0,"end"); self.cmd_preview.insert(0, disp)

    def _copy_cmd(self):
        self.clipboard_clear(); self.clipboard_append(self.cmd_preview.get())

    # ---------- Single run ----------
    def _run_clicked(self):
        if self.current_runner:
            self.current_runner.terminate(); self.current_runner=None
            self.run_btn.configure(text="▶ Run"); return
        cmd = self._assemble_cmd()
        env = os.environ.copy()
        for line in self.env_lines.get().splitlines():
            if "=" in line:
                k,v=line.split("=",1); env[k.strip()]=v.strip()
        self.output.delete("1.0","end")
        self._log(self.output, f"Running: {' '.join(cmd)}\n\n")
        self.run_btn.configure(text="■ Stop")
        def on_out(s): self._log(self.output, s)
        def on_err(s): self._log(self.output, s, err=True)
        def on_done(rc):
            self.run_btn.configure(text="▶ Run")
            self._log(self.output, f"\n[Process exited with {rc}]\n")
            self.current_runner=None
        self.current_runner = LiveRunner(cmd, cwd=Path(self.workdir.get()) if self.workdir.get() else None,
                                         env=env, on_stdout=on_out, on_stderr=on_err, on_done=on_done)
        self.current_runner.start()

    # ---------- Pipeline CRUD ----------
    def _pipe_add(self):
        d = StepDialog(self, title="New Step")
        self.wait_window(d)
        if d.result:
            self.steps.append(d.result)
            self._pipe_refresh()

    def _pipe_edit(self):
        idx=self._pipe_selindex()
        if idx is None: return
        d = StepDialog(self, title="Edit Step", preset=self.steps[idx])
        self.wait_window(d)
        if d.result:
            self.steps[idx]=d.result; self._pipe_refresh()

    def _pipe_remove(self):
        idx=self._pipe_selindex()
        if idx is None: return
        self.steps.pop(idx); self._pipe_refresh()

    def _pipe_move(self, delta):
        idx=self._pipe_selindex()
        if idx is None: return
        j = idx+delta
        if 0<=j<len(self.steps):
            self.steps[idx], self.steps[j] = self.steps[j], self.steps[idx]
            self._pipe_refresh(select=j)

    def _pipe_selindex(self):
        s=self.steps_lb.curselection()
        return s[0] if s else None

    def _pipe_refresh(self, select=None):
        self.steps_lb.delete(0,'end')
        for i,st in enumerate(self.steps):
            label=f"{i+1}. {Path(st['program']).name}  | args: {st['args']}  | capture: {st['capture_regex']}"
            self.steps_lb.insert('end', label)
        if select is not None:
            self.steps_lb.selection_set(select)

    def _pipe_save(self):
        name = simple_prompt(self, "Save Pipeline As", "Name:")
        if not name: return
        store={}
        if PIPELINE_FILE.exists():
            try: store=json.loads(PIPELINE_FILE.read_text(encoding='utf-8'))
            except Exception: store={}
        store[name]=self.steps
        PIPELINE_FILE.write_text(json.dumps(store, indent=2), encoding='utf-8')
        messagebox.showinfo("Saved", f"Pipeline '{name}' saved.")

    def _pipe_load(self):
        store={}
        if PIPELINE_FILE.exists():
            try: store=json.loads(PIPELINE_FILE.read_text(encoding='utf-8'))
            except Exception: store={}
        if not store:
            messagebox.showerror("None", "No pipelines saved yet."); return
        win=tk.Toplevel(self); win.title("Load Pipeline")
        lb=tk.Listbox(win, width=40, height=10); lb.pack(fill='both', expand=True, padx=8, pady=8)
        keys=sorted(store.keys())
        for k in keys: lb.insert('end', k)
        def pick(_e=None):
            s=lb.curselection();
            if not s: return
            self.steps = store[keys[s[0]]]
            self._pipe_refresh(); win.destroy()
        lb.bind('<Double-1>', pick)
        ttk.Button(win, text='Load', command=pick).pack(pady=(0,8))

    # ---------- Pipeline run ----------
    def _run_pipeline(self):
        if not self.steps:
            messagebox.showerror("Empty", "Add at least one step."); return
        self.pipe_output.delete('1.0','end')
        self.pipe_btn.configure(text="■ Running…", state='disabled')
        def worker():
            prev_path = ""
            for idx, st in enumerate(self.steps, start=1):
                prog = Path(st['program'])
                args_template = st['args']
                wd = st.get('workdir') or str(Path.cwd())
                env_add = st.get('env','')
                capture = st.get('capture_regex') or r"(?:saved to|into)\s+(.+)"  # default heuristic

                # Build env
                env=os.environ.copy()
                for line in (env_add or '').splitlines():
                    if "=" in line:
                        k,v=line.split("=",1); env[k.strip()]=v.strip()

                # Expand {prev}
                argline = (args_template or '').replace('{prev}', prev_path)
                cmd = guess_invocation(prog) + shlex.split(argline)
                self._log(self.pipe_output, f"\n▶ Step {idx}/{len(self.steps)}: {' '.join(cmd)}\n\n")

                try:
                    proc = subprocess.Popen(cmd, cwd=wd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                except Exception as e:
                    self._log(self.pipe_output, f"[Launch error] {e}\n", err=True)
                    break

                # stream output and try capture
                cap = None
                rx = re.compile(capture)
                for line in iter(proc.stdout.readline, ""):
                    self._log(self.pipe_output, line)
                    m = rx.search(line.strip())
                    if m:
                        cand = m.group(1).strip()
                        if os.path.exists(cand):
                            cap = cand
                rc = proc.wait()
                self._log(self.pipe_output, f"[Step {idx} exited {rc}]\n")
                if rc!=0:
                    self._log(self.pipe_output, "Pipeline halted due to non-zero exit.\n", err=True)
                    break
                prev_path = cap or prev_path  # carry forward if captured
            self.pipe_btn.configure(text="▶ Run Pipeline", state='normal')
        threading.Thread(target=worker, daemon=True).start()

    # ---------- Logging ----------
    def _log(self, widget: tk.Text, text: str, err: bool=False):
        widget.insert('end', text, 'stderr' if err else 'stdout'); widget.see('end')

# -------------- Dialogs --------------
class StepDialog(tk.Toplevel):
    def __init__(self, master, title="Step", preset=None):
        super().__init__(master)
        self.title(title)
        self.result=None
        f=ttk.Frame(self, padding=10); f.pack(fill='both', expand=True)
        self.var_prog=tk.StringVar(value=(preset or {}).get('program',''))
        self.var_args=tk.StringVar(value=(preset or {}).get('args',''))
        self.var_wd=tk.StringVar(value=(preset or {}).get('workdir',''))
        self.var_env=tk.StringVar(value=(preset or {}).get('env',''))
        self.var_rx=tk.StringVar(value=(preset or {}).get('capture_regex', r"(?:saved to|into)\s+(.+)"))

        row=0
        ttk.Label(f, text="Program:").grid(row=row,column=0,sticky='w');
        ttk.Entry(f, textvariable=self.var_prog, width=56).grid(row=row,column=1,sticky='ew');
        ttk.Button(f, text="…", command=self._pick_prog).grid(row=row,column=2, padx=6)
        row+=1
        ttk.Label(f, text="Args (use {prev} for previous output path):").grid(row=row,column=0,sticky='w')
        ttk.Entry(f, textvariable=self.var_args).grid(row=row,column=1,columnspan=2,sticky='ew'); row+=1
        ttk.Label(f, text="Working dir:").grid(row=row,column=0,sticky='w')
        ttk.Entry(f, textvariable=self.var_wd).grid(row=row,column=1,sticky='ew')
        ttk.Button(f, text="…", command=self._pick_wd).grid(row=row,column=2)
        row+=1
        ttk.Label(f, text="Env (KEY=VALUE per line):").grid(row=row,column=0,sticky='w')
        ttk.Entry(f, textvariable=self.var_env).grid(row=row,column=1,columnspan=2,sticky='ew'); row+=1
        ttk.Label(f, text="Capture regex (group1 = output path):").grid(row=row,column=0,sticky='w')
        ttk.Entry(f, textvariable=self.var_rx).grid(row=row,column=1,columnspan=2,sticky='ew'); row+=1

        btns=ttk.Frame(f); btns.grid(row=row,column=0,columnspan=3, pady=(8,0))
        ttk.Button(btns, text="OK", command=self._ok).pack(side='left', padx=6)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side='left')
        self.grab_set(); self.transient(master)

    def _pick_prog(self):
        p=filedialog.askopenfilename();
        if p: self.var_prog.set(p)
    def _pick_wd(self):
        d=filedialog.askdirectory();
        if d: self.var_wd.set(d)
    def _ok(self):
        if not Path(self.var_prog.get()).exists():
            messagebox.showerror("Missing", "Program not found."); return
        self.result={
            'program': self.var_prog.get(),
            'args': self.var_args.get(),
            'workdir': self.var_wd.get(),
            'env': self.var_env.get(),
            'capture_regex': self.var_rx.get(),
        }
        self.destroy()

# -------------- tiny prompt --------------
def simple_prompt(master, title, label):
    win=tk.Toplevel(master); win.title(title)
    var=tk.StringVar()
    ttk.Label(win, text=label).pack(padx=8, pady=(10,4))
    ent=ttk.Entry(win, textvariable=var, width=32); ent.pack(padx=8, pady=4); ent.focus_set()
    out={'v':None}
    def ok(): out['v']=var.get().strip(); win.destroy()
    ttk.Button(win, text='OK', command=ok).pack(pady=8)
    master.wait_window(win)
    return out['v']

# -------------- main --------------
def main():
    root=tk.Tk()
    try:
        style=ttk.Style(root); style.theme_use('clam')
    except Exception: pass
    app=App(root)
    root.mainloop()

if __name__=='__main__':
    main()
