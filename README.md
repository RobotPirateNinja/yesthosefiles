# DOJ Epstein Dataset PDF Downloader

This project contains scripts that download PDF files from the U.S. Department of Justice’s Epstein document dataset. The site sometimes asks you to prove you’re not a robot and confirm your age; these scripts let you do that once in a browser, then reuse that “login” to download many files automatically.

**You don’t need to know Python.** You only need to run a few commands in a terminal (Command Prompt on Windows, or Terminal on Mac/Linux).

---

## What you need first

1. **Python**  
   Python is a programming language; these scripts are written in it. You need Python **3.8 or newer** installed.

   - **Windows:** Download the installer from [python.org/downloads](https://www.python.org/downloads/). During setup, check **“Add Python to PATH”**.
   - **Mac:** Often already installed. If not, install from [python.org](https://www.python.org/downloads/) or with Homebrew: `brew install python3`.

   To check that it’s installed, open a terminal and type:
   ```text
   python --version
   ```
   You should see something like `Python 3.11.x`.

2. **A terminal (command line)**  
   - **Windows:** Open **Command Prompt** or **PowerShell** (search for “cmd” or “PowerShell” in the Start menu).
   - **Mac:** Open **Terminal** (search “Terminal” in Spotlight).

   You’ll run all the commands below in this window.

---

## Step 1: Open the project folder in the terminal

You need to be “inside” the project folder when you run the commands.

- **Windows (Command Prompt):**  
  `cd c:\repos\yesthosefiles`  
  (If your folder is somewhere else, use that path instead.)

- **Mac/Linux:**  
  `cd /path/to/yesthosefiles`  
  (Replace with the real path to the folder where the scripts live.)

---

## Step 2: Install the required libraries

The scripts use a few extra Python packages. Install them with:

```text
pip install -r requirements.txt
```

Then install the browser that the “login” step uses:

```text
playwright install chromium
```

If you see any errors, make sure Python and `pip` are in your PATH (see “What you need first” above).

---

## Step 3: Log in once (age/robot check)

The DOJ site may show an “I am not a robot” and age verification page. You only need to pass it once; the script will save the result and reuse it.

1. Decide **which script** you want to use:
   - **`get_em.py`** – one set of documents (DataSet 1, configurable in the script).
   - **`get_em_traunch_4.py`**, **`get_em_traunch_8.py`**, **`get_em_traunch_11.py`**, etc. – other batches; each has its own URL and file range defined at the top of the file.

2. Run the script with the **`--auth`** option. For example, for the 11th batch:

   ```text
   python get_em_traunch_11.py --auth
   ```

   A browser window will open to the first PDF. Complete the robot and age verification in that browser.

3. When you’re done, go back to the terminal and **press Enter** when the script asks you to. It will save your session into a file called `cookies.json` in the project folder.

After this, you usually don’t need to run `--auth` again unless the site logs you out or the cookies expire.

---

## Step 4: Run the download

Using the **same script** you used with `--auth`, run it **without** `--auth` to start downloading:

```text
python get_em_traunch_11.py
```

- PDFs are saved in the folder defined in that script (e.g. `downloads_11th_batch`). The script creates the folder if it doesn’t exist.
- It will skip files that are already in that folder.
- Many of these scripts are set to stop after about 5 minutes (`RUN_TIMEOUT_SECONDS`). You can run the same command again to continue; it will pick up where it left off.

**Optional:**

- **`--no-pause`** – no delay between requests (faster, but use with care to avoid overloading the server):
  ```text
  python get_em_traunch_11.py --no-pause
  ```
- **`--verify`** – test what the first URL returns (no login, no download):
  ```text
  python get_em_traunch_11.py --verify
  ```

---

## Summary of commands

| What you want to do              | Command                          |
|----------------------------------|----------------------------------|
| One-time login (browser opens)   | `python get_em_traunch_11.py --auth` |
| Download PDFs                    | `python get_em_traunch_11.py`    |
| Download with no delay           | `python get_em_traunch_11.py --no-pause` |
| Test first URL only              | `python get_em_traunch_11.py --verify` |

Replace `get_em_traunch_11.py` with `get_em.py` or any other `get_em_traunch_*.py` script you are using.

---

## Changing what gets downloaded

Each script has a **config block at the top** (right after the docstring). You can open the `.py` file in any text editor and change:

- **`BASE_URL`** – the DOJ dataset page (e.g. Data Set 1, 11, etc.).
- **`START_INDEX`** and **`END_INDEX`** – the range of file numbers (e.g. EFTA002205655 through EFTA002730264).
- **`OUTPUT_DIR`** – the folder where PDFs are saved (e.g. `downloads_11th_batch`).
- **`RUN_TIMEOUT_SECONDS`** – how long the download loop runs before stopping (e.g. 300 = 5 minutes). Run the script again to continue.

Save the file, then run the script as above.

---

## Files you might see

- **`cookies.json`** – Stores the session after you run `--auth`. Don’t share this file; treat it like a password.
- **`downloads_*`** folders – Where the downloaded PDFs are stored (name depends on the script’s `OUTPUT_DIR`).

---

## If something goes wrong

- **“No cookies.json found”**  
  Run the script with `--auth` first, complete the verification in the browser, then press Enter in the terminal.

- **“Install playwright”**  
  Run: `pip install playwright` then `playwright install chromium`.

- **Downloads stop or “session expired”**  
  Run `python get_em_traunch_11.py --auth` again (or the script you use), pass the verification, then run the script without `--auth` again.

- **Python not found**  
  Install Python from [python.org](https://www.python.org/downloads/) and make sure “Add Python to PATH” is checked (Windows).

---

## Quick reference: first time setup

```text
cd c:\repos\yesthosefiles
pip install -r requirements.txt
playwright install chromium
python get_em_traunch_11.py --auth
```

Then, after you verify in the browser and press Enter:

```text
python get_em_traunch_11.py
```

Use the same script name for both `--auth` and the normal run, and change the script name if you’re using a different batch (e.g. `get_em.py` or `get_em_traunch_8.py`).
