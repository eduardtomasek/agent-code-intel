"""Config loading — the four ENV/TOML existence states, the flat 13-key TOML
schema, hard type / syntax errors, the bash ENV harvester and the immutable
child environment (issue #51; ledger rows CFG-1…CFG-14, DEV-13, DEV-14).

Runs the real bash harvester in a subprocess — no stack, just ``bash`` on the
isolated PATH. Each case builds its own ``$CONF_DIR`` under a temp tree.
"""

import io
import os
import sys
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_code_intel import config
from agent_code_intel.config import ChildEnvironment, CliError, Config


class Base(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp(prefix="aci-config-")
        self.conf_dir = os.path.join(self.tmp, ".config", "code-intel")
        os.makedirs(self.conf_dir)
        self.cwd = self.tmp

    def write_env(self, text):
        with open(os.path.join(self.conf_dir, "defaults.env"), "w") as handle:
            handle.write(textwrap.dedent(text))

    def write_toml(self, text):
        with open(os.path.join(self.conf_dir, "defaults.toml"), "w") as handle:
            handle.write(textwrap.dedent(text))

    def load(self, environ=None):
        return config.load(
            self.conf_dir,
            environ if environ is not None else {"HOME": self.tmp, "PATH": os.environ["PATH"]},
            self.cwd,
            io.StringIO(),
        )


class ExistenceStates(Base):
    def test_neither_file_gives_builtin_defaults(self):
        loaded = self.load()
        self.assertEqual(loaded.source, "defaults")
        self.assertEqual(loaded.config, config.default_config())
        # meta.config_file reports defaults.toml even when nothing exists (CFG-1)
        self.assertTrue(loaded.config_file.endswith("defaults.toml"))

    def test_env_only_is_executed_as_bash(self):
        self.write_env("CHUNK_SIZE=999\n")
        loaded = self.load()
        self.assertEqual(loaded.source, "env")
        self.assertEqual(loaded.config.chunk_size, "999")
        self.assertTrue(loaded.config_file.endswith("defaults.env"))

    def test_toml_only_is_read_via_tomllib(self):
        self.write_toml("chunk_size = 512\n")
        loaded = self.load()
        self.assertEqual(loaded.source, "toml")
        self.assertEqual(loaded.config.chunk_size, "512")

    def test_both_files_is_a_hard_error_before_either_is_read(self):
        self.write_env("false\n")  # would kill the run if it were sourced
        self.write_toml("chunk_size = 1\n")
        with self.assertRaises(CliError) as caught:
            self.load()
        self.assertEqual(
            str(caught.exception),
            "%s: both defaults.env and defaults.toml exist; keep one" % self.conf_dir,
        )


class TomlSchema(Base):
    def test_thirteen_keys_all_accepted(self):
        self.write_toml(
            """
            qdrant_host = "example.test"
            qdrant_http_port = 7000
            qdrant_port = 7001
            qdrant_container = "c"
            qdrant_image = "img"
            qdrant_volume = "vol"
            ollama_http = "http://o:1"
            embed_provider = "openai"
            embed_model = "m"
            chunk_size = 64
            chunk_overlap = 8
            extra_ignores = ["a", "b"]
            gitignore_entries = []
            """
        )
        cfg = self.load().config
        self.assertEqual(cfg.qdrant_host, "example.test")
        self.assertEqual(cfg.qdrant_http_port, "7000")  # int stringified (CFG-5)
        self.assertEqual(cfg.chunk_overlap, "8")
        self.assertEqual(cfg.extra_ignores, ("a", "b"))
        self.assertEqual(cfg.gitignore_entries, ())  # empty array = empty list

    def test_unknown_key_is_a_hard_error(self):
        self.write_toml("chunk_sze = 5\n")
        with self.assertRaises(CliError) as caught:
            self.load()
        self.assertEqual(
            str(caught.exception),
            "%s/defaults.toml: unknown key 'chunk_sze'" % self.conf_dir,
        )

    def test_wrong_type_is_a_hard_error(self):
        self.write_toml('chunk_size = "big"\n')
        with self.assertRaises(CliError) as caught:
            self.load()
        self.assertEqual(
            str(caught.exception),
            "%s/defaults.toml: key 'chunk_size' must be an integer, got string"
            % self.conf_dir,
        )

    def test_string_key_given_an_integer_is_a_hard_error(self):
        self.write_toml("embed_model = 3\n")
        with self.assertRaises(CliError) as caught:
            self.load()
        self.assertIn("must be a string, got integer", str(caught.exception))

    def test_array_key_given_a_string_is_a_hard_error(self):
        self.write_toml('extra_ignores = "nope"\n')
        with self.assertRaises(CliError) as caught:
            self.load()
        self.assertIn("must be an array of strings, got string", str(caught.exception))

    def test_boolean_is_not_accepted_for_an_integer_key(self):
        self.write_toml("chunk_size = true\n")
        with self.assertRaises(CliError) as caught:
            self.load()
        self.assertIn("must be an integer, got boolean", str(caught.exception))

    def test_unparsable_toml_passes_the_tomllib_message_through(self):
        self.write_toml("chunk_size = = 3\n")
        with self.assertRaises(CliError) as caught:
            self.load()
        message = str(caught.exception)
        self.assertTrue(message.startswith("%s/defaults.toml: " % self.conf_dir))
        self.assertIn("line 1", message)

    def test_well_typed_out_of_range_value_is_not_validated(self):
        # A range/enum check would reject config the ENV path accepts (issue #37 §5)
        self.write_toml('embed_provider = "not-a-real-provider"\nqdrant_port = -1\n')
        cfg = self.load().config
        self.assertEqual(cfg.embed_provider, "not-a-real-provider")
        self.assertEqual(cfg.qdrant_port, "-1")

    def test_toml_does_no_expansion(self):
        self.write_toml('qdrant_container = "$QDRANT_HOST-box"\n')
        self.assertEqual(self.load().config.qdrant_container, "$QDRANT_HOST-box")


class EnvHarvester(Base):
    def test_bash_expansion_and_references_to_presets(self):
        self.write_env('QDRANT_CONTAINER="$QDRANT_HOST-box"\n')
        self.assertEqual(self.load().config.qdrant_container, "127.0.0.1-box")

    def test_default_when_env_touches_nothing(self):
        self.write_env("# empty\n")
        self.assertEqual(self.load().config, config.default_config())

    def test_array_replace_not_extend(self):
        self.write_env('EXTRA_IGNORES=(only.lock "with space.txt")\n')
        self.assertEqual(
            self.load().config.extra_ignores, ("only.lock", "with space.txt")
        )

    def test_empty_array_is_an_empty_list(self):  # DEV-14
        self.write_env("EXTRA_IGNORES=()\nGITIGNORE_ENTRIES=()\n")
        cfg = self.load().config
        self.assertEqual(cfg.extra_ignores, ())
        self.assertEqual(cfg.gitignore_entries, ())

    def test_unset_of_a_transferred_name_is_a_hard_error(self):  # CFG-11 / TXT-7
        self.write_env("unset QDRANT_HOST\n")
        with self.assertRaises(CliError) as caught:
            self.load()
        self.assertEqual(
            str(caught.exception),
            "%s/defaults.env: configuration name 'QDRANT_HOST' was unset"
            % self.conf_dir,
        )
        self.assertTrue(caught.exception.wrap)

    def test_non_zero_command_kills_the_run_silently(self):  # issue #38 §2.11
        self.write_env("false\n")
        with self.assertRaises(CliError) as caught:
            self.load()
        self.assertFalse(caught.exception.wrap)
        self.assertEqual(caught.exception.code, 1)

    def test_newlines_and_tabs_survive_the_transfer(self):
        self.write_env('EMBED_MODEL="a\tb"\n')
        self.assertEqual(self.load().config.embed_model, "a\tb")

    def test_conf_paths_are_transferred(self):  # 16-name inventory
        self.write_env("REGISTRY=/somewhere/else\n")
        loaded = self.load()
        self.assertEqual(loaded.conf_paths["REGISTRY"], "/somewhere/else")
        self.assertTrue(loaded.conf_paths["CONF_DIR"].endswith("code-intel"))

    def test_scalar_written_as_an_array_takes_the_first_element(self):
        self.write_env("QDRANT_HOST=(first second)\n")
        self.assertEqual(self.load().config.qdrant_host, "first")


class ChildEnv(Base):
    def test_export_reaches_the_child_env_without_touching_os_environ(self):  # CFG-12
        self.write_env("export ACI_UNIT_EXPORTED=yes\n")
        os.environ.pop("ACI_UNIT_EXPORTED", None)
        environ = {"HOME": self.tmp, "PATH": os.environ["PATH"]}
        loaded = self.load(environ)
        self.assertEqual(loaded.child_env["ACI_UNIT_EXPORTED"], "yes")
        self.assertIsNone(os.environ.get("ACI_UNIT_EXPORTED"))
        self.assertIsNone(environ.get("ACI_UNIT_EXPORTED"))

    def test_child_env_is_read_only(self):
        env = ChildEnvironment({"A": "1"})
        with self.assertRaises(TypeError):
            env["B"] = "2"  # type: ignore[index]

    def test_toml_run_child_env_is_a_plain_copy(self):
        self.write_toml("chunk_size = 1\n")
        loaded = self.load({"HOME": self.tmp, "FOO": "bar"})
        self.assertEqual(loaded.child_env["FOO"], "bar")

    def test_missing_bash_is_a_hard_error(self):  # CFG-10 / TXT-6
        self.write_env("CHUNK_SIZE=1\n")
        with self.assertRaises(CliError) as caught:
            # a PATH with no bash on it
            self.load({"HOME": self.tmp, "PATH": self.tmp})
        self.assertEqual(
            str(caught.exception),
            "bash is required to load %s/defaults.env" % self.conf_dir,
        )


class Immutability(unittest.TestCase):
    def test_config_is_frozen(self):
        cfg = config.default_config()
        with self.assertRaises(Exception):
            cfg.chunk_size = "9"  # type: ignore[misc]
        self.assertIsInstance(cfg, Config)


if __name__ == "__main__":
    unittest.main()
