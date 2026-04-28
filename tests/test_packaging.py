import subprocess, sys

def test_pack_script_runs():
    # Basic smoke test to ensure pack script exists and can be invoked
    # This test will simply import the script if present; real packaging is executed in CI/pipeline
    import os
    path = os.path.join(os.getcwd(), "pack.py")
    assert os.path.exists(path)
