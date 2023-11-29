import argparse
import contextlib
import os
import re
import sys

import requests

import NyaaPy

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser( description="Download batch torrents from Nyaasi" )

    parser.add_argument("name", type=str, help="Name of the anime to search for")
    parser.add_argument("-r", "--range", type=str,
                        help="Range of episodes in the form n-N to download episodes from n to N or n- to download"
                             " episodes from n to whenever it ends")
    parser.add_argument("-e", "--episode", type=int, help="Download a specific episode")
    parser.add_argument("-q", "--quality", type=int, default=1080, help="Set the quality to look for.")
    parser.add_argument("-d", "--directory", type=str, help="Download to specified directory."
                                                            " Defaults to given anime name")

    return parser.parse_args()

class UserError(Exception):
    msg: str

class NyaaBatch:
    def __init__(self):
        self.nyaa = NyaaPy.Nyaa
        self.torrents: list = []
        self.missing: list = []

    def find(self,
             name: str,
             episode: int,
             quality: int,
             untrusted: bool = False,
             allow_closest: bool = False) -> None:
        """
        Find anime matching :name:
        By default, prompt user for choice when multiple entries are found
        """
        episode_str: str = str(episode) if episode >= 10 else f"0{episode}"

        query = f"{name} - {episode_str}"
        found = self.nyaa.search(keyword=f"{query} [{quality}p]",
                                 category=1,
                                 subcategory=2,
                                 filters=2 if not untrusted else 0)
        found += self.nyaa.search(keyword=f"{query} ({quality}p)",
                                  category=1,
                                  subcategory=2,
                                  filters=2 if not untrusted else 0)

        if not found:
            raise FileNotFoundError(f"Unable to find {query}")

        # Sort the list of found torrents by the number of seeders
        found.sort(key=lambda i: i['seeders'], reverse=True)

        matching_torrent = None
        for torrent in found:
            torrent_name: str = torrent["name"]
            if re.search(query.lower(), torrent_name.lower()):
                matching_torrent = torrent
                break

            if allow_closest:
                if (re.search(name, torrent_name.lower()) and
                    re.search(episode_str, torrent_name.lower()) and
                    not re.search('~', torrent_name.lower())):
                    matching_torrent = torrent
                    break

        # There isn't an exact match and closest match is not allowed
        if matching_torrent is None:
            choices = {}
            print(f"Found multiple matches for {query}:")
            for i, t in enumerate(found):
                choices[i] = t
                print(f"\t{i}: {t['name']}")
            choice = int(input("Choose: ") or "0")
            matching_torrent = choices[choice]

        print(f"Found {matching_torrent['name']}, seeders: {matching_torrent['seeders']}")
        self.torrents.append((episode, matching_torrent))
        self.torrents.sort(key=lambda i: i[0])

    def download(self) -> None:
        """
        Download found episodes
        """
        if not self.torrents:
            raise UserError("No torrents to download")
        for ep, torrent in self.torrents:
            try:
                print(f"Downloading {torrent['name']}", end='... ')
                with requests.get(torrent["download_url"],
                                  timeout=60) as response, open(
                                      torrent["name"] + ".torrent",
                                      "wb") as out_file:
                    out_file.write(response.content)
            except requests.Timeout:
                print("FAILED")
                self.missing.append(ep)
                self.missing.sort()
                continue
            print("SUCCESS")

    def last(self) -> dict:
        return self.torrents[-1]

def run() -> None:
    opts = parse_args()

    start_ep = 1
    end_ep = None
    if opts.range:
        start_ep, end_ep = opts.range.split('-')
        start_ep = int(start_ep)
        if end_ep:
            end_ep = int(end_ep)

    if opts.episode:
        start_ep = opts.episode
        end_ep = start_ep + 1

    if end_ep is None:
        end_ep = sys.maxsize

    name: str = opts.name

    batch = NyaaBatch()

    for ep_num in range(start_ep, end_ep + 1):
        try:
            batch.find(name, ep_num, opts.quality)
        except FileNotFoundError as e:
            print(e)
            print(f"Last episode found: EP{batch.last()[0]} - {batch.last()[1]['name']}")
            choice = input("Continue? [y/N] ") or "n"
            if choice.lower() == "n":
                break

    out_dir = f"{os.getcwd()}/{name}"
    if opts.directory:
        out_dir = opts.directory
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    with contextlib.chdir(out_dir):
        try:
            batch.download()
        except UserError as e:
            print(e)
            sys.exit(1)
    if batch.missing:
        print(f"Missing episodes: {', '.join(batch.missing)}")

if __name__ == "__main__":
    run()
