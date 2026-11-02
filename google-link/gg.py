#!/usr/bin/env python3

import sys
import webbrowser
from urllib.parse import urlencode

def main():

    if len(sys.argv) < 2:
        print("Usage: gg <search query>")
        return


    query = " ".join(sys.argv[1:])

    url = "https://www.google.com/search?" + urlencode({
        "q": query
    })

    webbrowser.open(url)

if __name__ == "__main__":
        main()