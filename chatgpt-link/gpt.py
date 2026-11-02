#!/usr/bin/env python3

import sys
import webbrowser
import subprocess
import shutil


def main():

    if len(sys.argv) < 2:
        print("Usage: gpt <question>")
        return


    question = " ".join(sys.argv[1:])

    if shutil.which("wl-copy"):

        subprocess.run(
            ["wl-copy"],
            input=question,
            text=True,
            check=True
        )

    webbrowser.open("https://chatgpt.com/")

if __name__ == "__main__":
        main()