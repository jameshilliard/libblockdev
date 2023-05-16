import unittest
import os
import resource
import overrides_hack

from utils import create_sparse_tempfile, create_lio_device, delete_lio_device, fake_utils, fake_path, run_command, run, TestTags, tag_test
from gi.repository import BlockDev, GLib


class SwapTest(unittest.TestCase):
    requested_plugins = BlockDev.plugin_specs_from_names(("swap",))
    dev_size = 1024**3

    @classmethod
    def setUpClass(cls):
        if not BlockDev.is_initialized():
            BlockDev.init(cls.requested_plugins, None)
        else:
            BlockDev.reinit(cls.requested_plugins, True, None)

class SwapTestCase(SwapTest):
    def setUp(self):
        self.addCleanup(self._clean_up)
        self.dev_file = create_sparse_tempfile("swap_test", self.dev_size)
        try:
            self.loop_dev = create_lio_device(self.dev_file)
        except RuntimeError as e:
            raise RuntimeError("Failed to setup loop device for testing: %s" % e)

    def _clean_up(self):
        try:
            BlockDev.swap_swapoff(self.loop_dev)
        except:
            pass

        try:
            delete_lio_device(self.loop_dev)
        except RuntimeError:
            # just move on, we can do no better here
            pass
        os.unlink(self.dev_file)

    @tag_test(TestTags.CORE)
    def test_all(self):
        """Verify that swap_* functions work as expected"""

        with self.assertRaises(GLib.GError):
            BlockDev.swap_mkswap("/non/existing/device", None, None)

        with self.assertRaises(GLib.GError):
            BlockDev.swap_swapon("/non/existing/device", -1)

        with self.assertRaises(GLib.GError):
            BlockDev.swap_swapoff("/non/existing/device")

        self.assertFalse(BlockDev.swap_swapstatus("/non/existing/device"))

        # not a swap device (yet)
        with self.assertRaises(GLib.GError):
            BlockDev.swap_swapon(self.loop_dev, -1)

        with self.assertRaises(GLib.GError):
            BlockDev.swap_swapoff(self.loop_dev)

        on = BlockDev.swap_swapstatus(self.loop_dev)
        self.assertFalse(on)

        # the common/expected sequence of calls
        succ = BlockDev.swap_mkswap(self.loop_dev, None, None)
        self.assertTrue(succ)

        succ = BlockDev.swap_set_label(self.loop_dev, "BlockDevSwap")
        self.assertTrue(succ)

        _ret, out, _err = run_command("blkid -ovalue -sLABEL -p %s" % self.loop_dev)
        self.assertEqual(out, "BlockDevSwap")

        succ = BlockDev.swap_swapon(self.loop_dev, -1)
        self.assertTrue(succ)

        on = BlockDev.swap_swapstatus(self.loop_dev)
        self.assertTrue(on)

        succ = BlockDev.swap_swapoff(self.loop_dev)
        self.assertTrue(succ)

        # already off
        with self.assertRaises(GLib.GError):
            BlockDev.swap_swapoff(self.loop_dev)

        on = BlockDev.swap_swapstatus(self.loop_dev)
        self.assertFalse(on)

    def test_mkswap_with_label(self):
        """Verify that mkswap with label works as expected"""

        succ = BlockDev.swap_mkswap(self.loop_dev, "BlockDevSwap", None)
        self.assertTrue(succ)

        _ret, out, _err = run_command("blkid -ovalue -sLABEL -p %s" % self.loop_dev)
        self.assertEqual(out, "BlockDevSwap")

    def test_swapon_pagesize(self):
        """Verify that activating swap with different pagesize fails"""

        # pick some wrong page size: 8k on 64k and 64k everywhere else
        pagesize = resource.getpagesize()
        if pagesize == 65536:
            wrong_pagesize = 8192
        else:
            wrong_pagesize = 65536

        # create swap with "wrong" pagesize
        ret, out, err = run_command("mkswap --pagesize %s %s" % (wrong_pagesize, self.loop_dev))
        if ret != 0:
            self.fail("Failed to prepare swap for pagesize test: %s %s" % (out, err))

        # activation should fail because swap has different pagesize
        with self.assertRaises(BlockDev.SwapPagesizeError):
            BlockDev.swap.swapon(self.loop_dev)

    def test_swapon_wrong_size(self):
        """Verify that activating swap with a wrong size fails with expected exception"""

        # create swap bigger than the device (twice as big in 1024 sectors)
        ret, out, err = run_command("mkswap -f %s %d" % (self.loop_dev, (self.dev_size * 2) / 1024))
        if ret != 0:
            self.fail("Failed to prepare swap for wrong size test: %s %s" % (out, err))

        # activation should fail because swap is bigger than the underlying device
        with self.assertRaises(BlockDev.SwapActivateError):
            BlockDev.swap.swapon(self.loop_dev)

    def _remove_map(self, map_name):
        run("dmsetup remove -f %s" % map_name)

    @tag_test(TestTags.REGRESSION)
    def test_swapstatus_dm(self):
        """Verify that swapstatus works correctly with DM devices"""

        dm_name = "swapstatus-test"

        self.addCleanup(self._remove_map, dm_name)
        run("dmsetup create %s --table \"0 $((`lsblk -osize -b %s -nd`/512)) linear %s 0\"" % (dm_name, self.loop_dev, self.loop_dev))

        succ = BlockDev.swap_mkswap("/dev/mapper/%s" % dm_name, None, None)
        self.assertTrue(succ)

        on = BlockDev.swap_swapstatus("/dev/mapper/%s" % dm_name)
        self.assertFalse(on)

        succ = BlockDev.swap_swapon("/dev/mapper/%s" % dm_name, -1)
        self.assertTrue(succ)

        on = BlockDev.swap_swapstatus("/dev/mapper/%s" % dm_name)
        self.assertTrue(on)

        succ = BlockDev.swap_swapoff("/dev/mapper/%s" % dm_name)
        self.assertTrue(succ)

        on = BlockDev.swap_swapstatus("/dev/mapper/%s" % dm_name)
        self.assertFalse(on)


class SwapUnloadTest(SwapTest):
    def setUp(self):
        # make sure the library is initialized with all plugins loaded for other
        # tests
        self.addCleanup(BlockDev.reinit, self.requested_plugins, True, None)

    @tag_test(TestTags.NOSTORAGE)
    def test_check_low_version(self):
        """Verify that checking the minimum swap utils versions works as expected"""

        # unload all plugins first
        self.assertTrue(BlockDev.reinit([], True, None))

        with fake_utils("tests/swap_low_version/"):
            # too low version of mkswap available, the swap plugin should fail to load
            with self.assertRaises(GLib.GError):
                BlockDev.reinit(self.requested_plugins, True, None)

            self.assertNotIn("swap", BlockDev.get_available_plugin_names())

        # load the plugins back
        self.assertTrue(BlockDev.reinit(self.requested_plugins, True, None))
        self.assertIn("swap", BlockDev.get_available_plugin_names())

    @tag_test(TestTags.NOSTORAGE)
    def test_check_no_mkswap(self):
        """Verify that checking mkswap and swaplabel tools availability
           works as expected
        """

        # unload all plugins first
        self.assertTrue(BlockDev.reinit([], True, None))

        with fake_path(all_but="mkswap"):
            # no mkswap available, the swap plugin should fail to load
            with self.assertRaises(GLib.GError):
                BlockDev.reinit(self.requested_plugins, True, None)

            self.assertNotIn("swap", BlockDev.get_available_plugin_names())

        with fake_path(all_but="swaplabel"):
            # no swaplabel available, the swap plugin should fail to load
            with self.assertRaises(GLib.GError):
                BlockDev.reinit(self.requested_plugins, True, None)

            self.assertNotIn("swap", BlockDev.get_available_plugin_names())

        # load the plugins back
        self.assertTrue(BlockDev.reinit(self.requested_plugins, True, None))
        self.assertIn("swap", BlockDev.get_available_plugin_names())

    @tag_test(TestTags.NOSTORAGE)
    def test_check_no_mkswap_runtime(self):
        """Verify that runtime checking mkswap tool availability works as expected"""

        # unload all plugins first
        self.assertTrue(BlockDev.reinit([], True, None))

        # make sure the initial checks during plugin loading are skipped
        BlockDev.switch_init_checks(False)
        self.addCleanup(BlockDev.switch_init_checks, True)

        with fake_path(all_but="mkswap"):
            # no mkswap available, but checks disabled, the swap plugin should load just fine
            self.assertTrue(BlockDev.reinit(self.requested_plugins, True, None))
            self.assertIn("swap", BlockDev.get_available_plugin_names())

            with self.assertRaisesRegexp(GLib.GError, "The 'mkswap' utility is not available"):
                # the device shouldn't matter, the function should return an
                # error before any other checks or actions
                BlockDev.swap_mkswap("/dev/device", "LABEL", None)

class SwapTechAvailable(SwapTest):
    def setUp(self):
        # set everything back and reinit just to be sure
        self.addCleanup(BlockDev.switch_init_checks, True)
        self.addCleanup(BlockDev.reinit, self.requested_plugins, True, None)

    @tag_test(TestTags.NOSTORAGE)
    def test_check_tech_available(self):
        """Verify that runtime checking mkswap and swaplabel tools availability
           works as expected
        """

        with fake_path(all_but="mkswap"):
            BlockDev.switch_init_checks(False)
            BlockDev.reinit(self.requested_plugins, True, None)

            with self.assertRaises(GLib.GError):
                # we have swaplabel but not mkswap, so this should fail
                BlockDev.swap_is_tech_avail(BlockDev.SwapTech.SWAP_TECH_SWAP,
                                            BlockDev.SwapTechMode.CREATE | BlockDev.SwapTechMode.SET_LABEL)

            with self.assertRaises(GLib.GError):
                # we have swaplabel but not mkswap, so this should fail
                BlockDev.swap_is_tech_avail(BlockDev.SwapTech.SWAP_TECH_SWAP,
                                            BlockDev.SwapTechMode.CREATE)

            # only label checked -- should pass
            succ = BlockDev.swap_is_tech_avail(BlockDev.SwapTech.SWAP_TECH_SWAP,
                                               BlockDev.SwapTechMode.SET_LABEL)
            self.assertTrue(succ)

        with fake_path(all_but="swaplabel"):
            BlockDev.switch_init_checks(False)
            BlockDev.reinit(self.requested_plugins, True, None)

            with self.assertRaises(GLib.GError):
                # we have mkswap but not swaplabel, so this should fail
                BlockDev.swap_is_tech_avail(BlockDev.SwapTech.SWAP_TECH_SWAP,
                                            BlockDev.SwapTechMode.CREATE | BlockDev.SwapTechMode.SET_LABEL)

            with self.assertRaises(GLib.GError):
                # we have mkswap but not swaplabel, so this should fail
                BlockDev.swap_is_tech_avail(BlockDev.SwapTech.SWAP_TECH_SWAP,
                                            BlockDev.SwapTechMode.SET_LABEL)

            # only label checked -- should pass
            succ = BlockDev.swap_is_tech_avail(BlockDev.SwapTech.SWAP_TECH_SWAP,
                                               BlockDev.SwapTechMode.CREATE)
            self.assertTrue(succ)
