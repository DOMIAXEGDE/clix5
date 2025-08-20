# text.py
# A runtime programmable Python 3.13.5 console application for Windows 11 Pro and Linux.
# This script functions as a workbench text editor with integrated shell command execution
# and simple C++ code compilation.
#
# VERSION 2 - STABILITY FIX
# - Reworked screen drawing logic to prevent 'addwstr() returned ERR' crashes.
# - The status bar is now drawn more safely to avoid writing to the edge of the screen.
#
# USAGE:
# 1. Save this file as 'text.py'.
# 2. Make sure you have the 'windows-curses' library installed:
#    pip install windows-curses
# 3. Run from your terminal:
#    python text.py [optional_filename.txt]
#
# EDITOR CONTROLS:
# - Type normally to edit text.
# - Use Arrow Keys to navigate.
# - Backspace/Delete: Deletes characters.
# - Enter: Creates a new line.
# - ESC: Toggles between EDIT and COMMAND mode.
#
# COMMAND MODE (Press ESC to enter, ':' will appear at the bottom):
# - :w [filename]   - Write (save) the file. If no filename is given, uses the current name.
# - :o [filename]   - Open a file.
# - :q              - Quit the editor. (Will warn if there are unsaved changes).
# - :q!             - Force quit without saving.
# - :! <command>    - Execute a shell command. The output will be inserted into the text.
# - :cpp            - Compile and run the current buffer as C++23, inserting program output.
# - :help           - Display the help screen.

import curses
import curses.ascii
import subprocess
import sys
import os

class TextEditor:
    """
    Encapsulates the state and behavior of the console text editor.
    It manages the text buffer, user input, screen drawing, file I/O,
    shell command execution, and a lightweight C++ compilation helper.
    """
    def __init__(self, stdscr, initial_file=None):
        """Initializes the editor state."""
        self.stdscr = stdscr
        self.buffer = [""]
        self.cursor_y, self.cursor_x = 0, 0
        self.offset_y, self.offset_x = 0, 0
        self.filename = initial_file if initial_file else "untitled.txt"
        self.status_message = "Press ESC for COMMAND mode"
        self.mode = "EDIT"  # Can be "EDIT" or "COMMAND"
        self.command_buffer = ""
        self.dirty = False # Tracks if the file has unsaved changes.

        if initial_file and os.path.exists(initial_file):
            self.open_file(initial_file)
            self.dirty = False # Reset dirty flag after initial load

    def run(self):
        """
        The main loop of the editor. It continuously waits for user input,
        processes it, and redraws the screen until the user quits.
        """
        self.stdscr.nodelay(False)
        self.stdscr.keypad(True)
        curses.curs_set(1)

        while True:
            self.draw()
            try:
                key = self.stdscr.getch()
            except (curses.error, KeyboardInterrupt):
                continue # Ignore errors on resize or Ctrl+C

            if self.mode == "COMMAND":
                if self.process_command_input(key):
                    break
            elif self.mode == "EDIT":
                self.process_edit_input(key)

    def safe_addstr(self, y, x, text, attr=0):
        """A wrapper for addstr that prevents crashes from writing off-screen."""
        try:
            self.stdscr.addstr(y, x, text, attr)
        except curses.error:
            # This can happen if the window is resized to be too small.
            # We just ignore the error to prevent a crash.
            pass

    def draw(self):
        """Refreshes the entire screen with the current editor state."""
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()

        # Draw the text buffer content
        for y, line in enumerate(self.buffer[self.offset_y:]):
            if y >= height - 1: # Stop before the status bar line
                break
            
            # Truncate line to fit screen width
            display_line = line[self.offset_x:]
            if len(display_line) >= width:
                display_line = display_line[:width - 1]
            
            self.safe_addstr(y, 0, display_line)

        # Draw the status bar at the bottom
        self.draw_status_bar(height, width)

        # Position the hardware cursor correctly, ensuring it's within bounds
        cursor_draw_y = self.cursor_y - self.offset_y
        cursor_draw_x = self.cursor_x - self.offset_x
        if 0 <= cursor_draw_y < height -1 and 0 <= cursor_draw_x < width -1:
             self.stdscr.move(cursor_draw_y, cursor_draw_x)

        self.stdscr.refresh()

    def draw_status_bar(self, height, width):
        """Draws the status bar safely to prevent screen overflow errors."""
        if height <= 0: return # Cannot draw if there's no screen height

        dirty_indicator = " [+]" if self.dirty else ""
        
        if self.mode == "COMMAND":
            status_text = f":{self.command_buffer}"
        else:
            status_text = self.status_message

        # Left-aligned info
        info_left = f" {self.mode} | {self.filename}{dirty_indicator} | L{self.cursor_y + 1}, C{self.cursor_x + 1} "
        
        # Right-aligned info
        info_right = f" {status_text} "

        # Calculate total length and available space for filling
        total_len = len(info_left) + len(info_right)
        fill_len = width - total_len
        if fill_len < 0:
            fill_len = 0

        # Construct the full status bar string
        full_bar = info_left + (' ' * fill_len) + info_right
        
        # Truncate the final string to be safe, ensuring it's not wider than the screen
        if len(full_bar) > width:
            full_bar = full_bar[:width]

        # Draw the bar and fill the remainder of the line
        self.safe_addstr(height - 1, 0, full_bar, curses.A_REVERSE)
        remaining_space = width - len(full_bar)
        if remaining_space > 0:
            self.safe_addstr(height - 1, len(full_bar), ' ' * remaining_space, curses.A_REVERSE)

    def insert_text(self, text):
        """Inserts a block of text at the current cursor position."""
        if not text:
            return

        output_lines = text.splitlines()
        current_line = self.buffer[self.cursor_y]
        before_cursor = current_line[:self.cursor_x]
        after_cursor = current_line[self.cursor_x:]

        self.buffer[self.cursor_y] = before_cursor + output_lines[0]
        for i, line in enumerate(output_lines[1:]):
            self.buffer.insert(self.cursor_y + 1 + i, line)

        self.cursor_y += len(output_lines) - 1
        self.cursor_x = len(self.buffer[self.cursor_y])
        self.buffer[self.cursor_y] += after_cursor
        self.dirty = True

    def show_help_screen(self):
        """Displays a full-screen help menu until a key is pressed."""
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()
        
        help_text = [
            "--- text.py Help ---",
            "",
            "text.py is a simple console-based text editor with integrated shell scripting.",
            "",
            "MODES",
            "  EDIT MODE:    Default mode. Type to insert text.",
            "  COMMAND MODE: Enter commands for file operations or to run shell scripts.",
            "  Press 'ESC' to switch from EDIT to COMMAND mode.",
            "",
            "EDIT MODE CONTROLS",
            "  Arrow Keys:   Navigate the text.",
            "  Enter:        Insert a new line.",
            "  Backspace:    Delete character to the left of the cursor.",
            "  Delete:       Delete character at the cursor position.",
            "",
            "COMMAND MODE COMMANDS (Enter by pressing ':' first)",
            "  :w [filename]   Save the current buffer to a file. If no filename is given,",
            "                  it uses the current file's name.",
            "  :o [filename]   Open a file. You will be warned if you have unsaved changes.",
            "  :q              Quit the editor. Fails if there are unsaved changes.",
            "  :q!             Force quit without saving any changes.",
            "  :help           Display this help screen.",
            "  :! <command>    Execute a shell command and insert its output at the cursor.",
            "                  Example: ':! ls -al'",
            "  :cpp            Compile and run the current buffer as C++23.",
            "                  Program output or compiler errors are inserted at the cursor.",
            "",
            "",
            "Press any key to return to the editor..."
        ]

        for i, line in enumerate(help_text):
            if i >= height - 1:
                break
            # Truncate line to be safe
            if len(line) >= width:
                line = line[:width - 1]
            self.safe_addstr(i, 2, line)

        self.stdscr.refresh()
        self.stdscr.getch() # Wait for user to press a key

    def process_edit_input(self, key):
        """Handles key presses when in EDIT mode."""
        height, width = self.stdscr.getmaxyx()
        
        if key == 27:  # ESC key
            self.mode = "COMMAND"
            self.status_message = ""
            self.command_buffer = ""
        elif key in (curses.KEY_ENTER, 10, 13):
            current_line = self.buffer[self.cursor_y]
            self.buffer[self.cursor_y] = current_line[:self.cursor_x]
            self.buffer.insert(self.cursor_y + 1, current_line[self.cursor_x:])
            self.cursor_y += 1
            self.cursor_x = 0
            self.dirty = True
        elif key in (curses.KEY_BACKSPACE, 8, 127):
            if self.cursor_x > 0:
                current_line = self.buffer[self.cursor_y]
                self.buffer[self.cursor_y] = current_line[:self.cursor_x - 1] + current_line[self.cursor_x:]
                self.cursor_x -= 1
                self.dirty = True
            elif self.cursor_y > 0:
                prev_line_len = len(self.buffer[self.cursor_y - 1])
                self.buffer[self.cursor_y - 1] += self.buffer.pop(self.cursor_y)
                self.cursor_y -= 1
                self.cursor_x = prev_line_len
                self.dirty = True
        elif key == curses.KEY_DC: # Delete key
            current_line = self.buffer[self.cursor_y]
            if self.cursor_x < len(current_line):
                self.buffer[self.cursor_y] = current_line[:self.cursor_x] + current_line[self.cursor_x+1:]
                self.dirty = True
            elif self.cursor_y < len(self.buffer) - 1:
                self.buffer[self.cursor_y] += self.buffer.pop(self.cursor_y + 1)
                self.dirty = True
        elif key == curses.KEY_UP:
            if self.cursor_y > 0:
                self.cursor_y -= 1
        elif key == curses.KEY_DOWN:
            if self.cursor_y < len(self.buffer) - 1:
                self.cursor_y += 1
        elif key == curses.KEY_LEFT:
            if self.cursor_x > 0:
                self.cursor_x -= 1
            elif self.cursor_y > 0:
                self.cursor_y -= 1
                self.cursor_x = len(self.buffer[self.cursor_y])
        elif key == curses.KEY_RIGHT:
            if self.cursor_x < len(self.buffer[self.cursor_y]):
                self.cursor_x += 1
            elif self.cursor_y < len(self.buffer) - 1:
                self.cursor_y += 1
                self.cursor_x = 0
        elif curses.ascii.isprint(key):
            self.buffer[self.cursor_y] = self.buffer[self.cursor_y][:self.cursor_x] + chr(key) + self.buffer[self.cursor_y][self.cursor_x:]
            self.cursor_x += 1
            self.dirty = True

        # Adjust cursor X if it's beyond the end of the new line
        if self.cursor_x > len(self.buffer[self.cursor_y]):
            self.cursor_x = len(self.buffer[self.cursor_y])

    def process_command_input(self, key):
        """Handles key presses when in COMMAND mode. Returns True if quit command is issued."""
        if key == 27:  # ESC key
            self.mode = "EDIT"
            self.status_message = "Press ESC for COMMAND mode"
        elif key in (curses.KEY_ENTER, 10, 13):
            should_quit = self.execute_command(self.command_buffer)
            self.command_buffer = ""
            if should_quit:
                return True
            self.mode = "EDIT"
        elif key in (curses.KEY_BACKSPACE, 8, 127):
            self.command_buffer = self.command_buffer[:-1]
        elif curses.ascii.isprint(key):
            self.command_buffer += chr(key)
        return False

    def execute_command(self, command):
        """Parses and executes a command. Returns True if the app should quit."""
        parts = command.strip().split()
        if not parts:
            self.status_message = ""
            return False

        cmd = parts[0]
        args = parts[1:]

        if cmd == 'q':
            if self.dirty:
                self.status_message = "Unsaved changes! Use :q! to force quit."
            else:
                return True # Signal to quit
        elif cmd == 'q!':
            return True # Signal to quit
        elif cmd == 'w':
            filename = args[0] if args else self.filename
            self.save_file(filename)
        elif cmd == 'help':
            self.show_help_screen()
        elif cmd == 'o':
            if args:
                if self.dirty:
                    self.status_message = "Unsaved changes! Save with :w first."
                else:
                    self.open_file(args[0])
            else:
                self.status_message = "Usage: :o <filename>"
        elif cmd == 'cpp':
            self.compile_and_run_cpp()
        elif cmd.startswith('!'):
            shell_command = command[1:].strip()
            self.execute_shell(shell_command)
        else:
            self.status_message = f"Unknown command: {cmd}"
        
        return False # Do not quit

    def execute_shell(self, shell_command):
        """Executes a shell command and inserts its output into the buffer."""
        if not shell_command:
            self.status_message = "No shell command provided."
            return

        self.status_message = f"Executing: {shell_command[:40]}..."
        self.draw()

        if os.name == 'nt':
            cmd = ['powershell', '-Command', shell_command]
        else:
            cmd = ['bash', '-lc', shell_command]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                check=False
            )

            output_to_insert = result.stderr if result.returncode != 0 and result.stderr else result.stdout
            self.status_message = "Command finished."

            if not output_to_insert.strip():
                self.status_message = "Command produced no output."
                return

            self.insert_text(output_to_insert.strip())

        except FileNotFoundError:
            self.status_message = "Error: shell not found."
        except Exception as e:
            self.status_message = f"Python Error: {str(e)}"

    def compile_and_run_cpp(self):
        """Compiles the current buffer as C++23 and inserts program output or errors."""
        source_code = "\n".join(self.buffer)
        self.status_message = "Compiling C++ code..."
        self.draw()

        try:
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                src_path = os.path.join(tmpdir, "main.cpp")
                exe_path = os.path.join(tmpdir, "a.out")
                if os.name == 'nt':
                    exe_path += '.exe'
                with open(src_path, 'w', encoding='utf-8') as f:
                    f.write(source_code)

                compile_cmd = ['g++', '-std=c++23', src_path, '-o', exe_path]
                compile_res = subprocess.run(
                    compile_cmd, capture_output=True, text=True, encoding='utf-8', errors='replace'
                )

                if compile_res.returncode != 0:
                    output = compile_res.stderr or "Compilation failed."
                    self.status_message = "Compilation failed."
                    self.insert_text(output.strip())
                    return

                run_res = subprocess.run(
                    [exe_path], capture_output=True, text=True, encoding='utf-8', errors='replace'
                )
                output = run_res.stdout
                if run_res.stderr:
                    output += ("\n" + run_res.stderr)
                if not output.strip():
                    output = "(program produced no output)"
                self.status_message = f"Program exited with code {run_res.returncode}"
                self.insert_text(output.strip())

        except FileNotFoundError:
            self.status_message = "g++ compiler not found."
        except Exception as e:
            self.status_message = f"Python Error: {str(e)}"

    def save_file(self, filename):
        """Saves the buffer content to a file."""
        try:
            with open(filename, "w", encoding='utf-8') as f:
                f.write("\n".join(self.buffer))
            self.filename = filename
            self.status_message = f"Saved {len(self.buffer)} lines to {filename}"
            self.dirty = False
        except Exception as e:
            self.status_message = f"Error saving file: {str(e)}"

    def open_file(self, filename):
        """Opens a file and loads its content into the buffer."""
        try:
            with open(filename, "r", encoding='utf-8') as f:
                self.buffer = [line.rstrip('\n\r') for line in f.readlines()]
        except FileNotFoundError:
            self.buffer = [""]
        except Exception as e:
            self.status_message = f"Error opening file: {str(e)}"
            return
        
        self.filename = filename
        self.cursor_y, self.cursor_x = 0, 0
        self.offset_y, self.offset_x = 0, 0
        self.status_message = f"Opened {filename}"
        self.dirty = False

def main(stdscr):
    """The main entry point called by curses.wrapper."""
    initial_file = sys.argv[1] if len(sys.argv) > 1 else None
    editor = TextEditor(stdscr, initial_file)
    editor.run()

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except curses.error as e:
        print(f"Curses initialization failed. Your terminal might not be supported.")
        print(f"Error: {e}")
    except Exception as e:
        # Gracefully exit and print any unexpected errors
        print("--- Editor crashed ---")
        print(f"An unexpected error occurred: {e}")
        # The crash recovery file is no longer needed with the stability fixes,
        # but you could re-enable it here if desired.
