from __future__ import annotations

import contextlib
import csv
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import ig_audit

TIMESTAMP = 1_700_000_000


def follower_record(username: str) -> dict:
    return {
        "string_list_data": [
            {
                "href": f"https://www.instagram.com/{username}/",
                "value": username,
                "timestamp": TIMESTAMP,
            }
        ]
    }


def following_record(username: str) -> dict:
    return {
        "title": username,
        "string_list_data": [
            {
                "href": f"https://www.instagram.com/{username}/",
                "value": username,
                "timestamp": TIMESTAMP,
            }
        ],
    }


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def default_folder(root: Path) -> Path:
    return root / "connections" / "followers_and_following"


def write_followers(path: Path, usernames: list[str]) -> None:
    write_json(path, [follower_record(name) for name in usernames])


def write_following(path: Path, usernames: list[str]) -> None:
    write_json(
        path,
        {"relationships_following": [following_record(name) for name in usernames]},
    )


def make_export(
    root: Path,
    followers: list[str],
    following: list[str],
) -> Path:
    folder = default_folder(root)
    write_followers(folder / "followers_1.json", followers)
    write_following(folder / "following.json", following)
    return root


def usernames(accounts: list[dict]) -> list[str]:
    return [account["username"] for account in accounts]


class ParserTests(unittest.TestCase):
    def test_current_export_format(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            export = make_export(
                Path(temporary),
                followers=["alice", "charlie", "drew", "Zoe"],
                following=["alice", "bob", "charlie", "drew", "Eve_99"],
            )

            payload = ig_audit.build_payload(export)

            self.assertEqual(payload["counts"]["following"], 5)
            self.assertEqual(payload["counts"]["followers"], 4)
            self.assertEqual(payload["counts"]["notFollowingBack"], 2)
            self.assertEqual(payload["counts"]["fans"], 1)
            self.assertEqual(payload["counts"]["mutual"], 3)
            self.assertEqual(usernames(payload["notFollowingBack"]), ["bob", "Eve_99"])
            self.assertEqual(usernames(payload["fans"]), ["Zoe"])

    def test_reads_all_split_follower_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = default_folder(root)
            write_followers(folder / "followers_1.json", ["alice", "casey"])
            write_followers(folder / "followers_2.json", ["drew"])
            write_following(folder / "following.json", ["alice", "bo", "casey", "drew"])

            payload = ig_audit.build_payload(root)

            self.assertEqual(payload["counts"]["followers"], 3)
            self.assertEqual(usernames(payload["notFollowingBack"]), ["bo"])

    def test_reads_split_following_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = default_folder(root)
            write_followers(folder / "followers_1.json", ["alice", "bob", "carol"])
            write_following(folder / "following_1.json", ["alice"])
            write_following(folder / "following_2.json", ["bob", "carol"])

            payload = ig_audit.build_payload(root)

            self.assertEqual(payload["counts"]["following"], 3)
            self.assertEqual(payload["counts"]["notFollowingBack"], 0)

    def test_reads_combined_relationships_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_json(
                root / "connections.json",
                {
                    "relationships_followers": [
                        follower_record("alice"),
                        follower_record("bob"),
                    ],
                    "relationships_following": [
                        following_record("alice"),
                        following_record("carol"),
                    ],
                },
            )

            payload = ig_audit.build_payload(root)

            self.assertEqual(usernames(payload["notFollowingBack"]), ["carol"])
            self.assertEqual(usernames(payload["mutual"]), ["alice"])

    def test_url_only_records_and_old_mobile_links(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = default_folder(root)
            write_json(
                folder / "followers_1.json",
                [
                    {
                        "string_list_data": [
                            {
                                "href": "https://www.instagram.com/_u/alice/?hl=en",
                                "timestamp": TIMESTAMP,
                            }
                        ]
                    }
                ],
            )
            write_json(
                folder / "following.json",
                {
                    "relationships_following": [
                        {"title": "alice"},
                        {"title": "bob"},
                    ]
                },
            )

            payload = ig_audit.build_payload(root)

            self.assertEqual(usernames(payload["notFollowingBack"]), ["bob"])
            self.assertEqual(usernames(payload["mutual"]), ["alice"])

    def test_case_insensitive_and_duplicate_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            export = make_export(
                Path(temporary),
                followers=["Alice", "alice", "BOB"],
                following=["alice", "bob", "Bob"],
            )

            payload = ig_audit.build_payload(export)

            self.assertEqual(payload["counts"]["followers"], 2)
            self.assertEqual(payload["counts"]["following"], 2)
            self.assertEqual(payload["counts"]["notFollowingBack"], 0)
            self.assertEqual(payload["counts"]["mutual"], 2)

    def test_empty_follower_list_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            export = make_export(
                Path(temporary), followers=[], following=["alice", "bob"]
            )

            payload = ig_audit.build_payload(export)

            self.assertEqual(payload["counts"]["notFollowingBack"], 2)
            self.assertEqual(usernames(payload["notFollowingBack"]), ["alice", "bob"])

    def test_sorted_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            export = make_export(
                Path(temporary),
                followers=[],
                following=["Zoe", "alice", "Bob", "_carol"],
            )

            payload = ig_audit.build_payload(export)

            self.assertEqual(
                usernames(payload["notFollowingBack"]),
                ["_carol", "alice", "Bob", "Zoe"],
            )

    def test_missing_relationship_list_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = default_folder(root)
            write_followers(folder / "followers_1.json", ["alice"])

            with self.assertRaises(ig_audit.AuditError):
                ig_audit.build_payload(root)

    def test_zip_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = default_folder(root)
            write_followers(folder / "followers_1.json", ["alice", "bob"])
            write_following(folder / "following.json", ["alice", "carol"])
            archive_path = root / "export.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                for path in folder.rglob("*.json"):
                    archive.write(path, path.relative_to(root).as_posix())

            payload = ig_audit.build_payload(archive_path)

            self.assertEqual(payload["source"], "export.zip")
            self.assertEqual(usernames(payload["notFollowingBack"]), ["carol"])

    def test_bad_path_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "not-json.txt").write_text("hello", encoding="utf-8")

            with self.assertRaises(ig_audit.AuditError):
                ig_audit.build_payload(root)


class OutputTests(unittest.TestCase):
    def test_cli_writes_all_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            export = make_export(
                root,
                followers=["alice", "bob"],
                following=["alice", "bob", "carol"],
            )
            out = root / "report" / "audit.html"
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                result = ig_audit.main([str(export), "--out", str(out)])

            self.assertEqual(result, 0)
            self.assertTrue(out.exists())
            self.assertIn(
                "Not following back:     1",
                stdout.getvalue(),
            )

            txt_path = root / "report" / "audit_not_following_back.txt"
            csv_path = root / "report" / "audit_accounts.csv"
            self.assertEqual(txt_path.read_text(encoding="utf-8"), "carol\n")

            with csv_path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(
                rows[0],
                {
                    "category": "not_following_back",
                    "username": "carol",
                    "profile_url": "https://www.instagram.com/carol/",
                    "timestamp_utc": "2023-11-14T22:13:20+00:00",
                },
            )

    def test_dashboard_contains_title_and_escaped_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            export = make_export(
                root,
                followers=["alice"],
                following=["alice", "bob"],
            )
            payload = ig_audit.build_payload(export)
            out = root / "audit.html"

            ig_audit.write_report(out, payload)
            document = out.read_text(encoding="utf-8")

            self.assertIn("<title>Local Instagram Unfollower</title>", document)
            self.assertIn('"username": "bob"', document)
            self.assertNotIn("</script><script>", document)

    def test_version_flag(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as raised:
                ig_audit.main(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn(ig_audit.VERSION, stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
