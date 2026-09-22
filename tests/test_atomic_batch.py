from pathlib import Path

import pytest

from igea_dgs.reporting import AtomicRunPublisher, RunManifest, sha256_file


class InjectedFailure(RuntimeError):
    pass


def test_failure_after_new_dgs_write_keeps_previous_release(tmp_path):
    final = tmp_path / "F1.dgs"
    final.write_text("KNOWN-GOOD", encoding="utf-8")

    with pytest.raises(InjectedFailure):
        with AtomicRunPublisher(tmp_path, "run-1", "F1") as publisher:
            publisher.stage_text("F1.dgs", "BROKEN-NEW")
            raise InjectedFailure("validation failed")

    assert final.read_text(encoding="utf-8") == "KNOWN-GOOD"
    assert not list((tmp_path / ".runs").glob("**/*.tmp"))


def test_commit_is_atomic_and_manifest_hashes_output(tmp_path):
    with AtomicRunPublisher(tmp_path, "run-2", "F1") as publisher:
        staged = publisher.stage_text("F1.dgs", "VALID")
        expected_hash = sha256_file(staged)
        manifest = RunManifest.create("run-2", "F1", outputs={"F1.dgs": expected_hash})
        publisher.stage_text("run_manifest.json", manifest.to_json())
        publisher.commit()

    assert (tmp_path / "F1.dgs").read_text(encoding="utf-8") == "VALID"
    assert sha256_file(tmp_path / "F1.dgs") == expected_hash
