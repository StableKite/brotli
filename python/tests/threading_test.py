import sys
import sysconfig
import unittest

import brotli


class ThreadingTests(unittest.TestCase):
  @unittest.skipUnless(sysconfig.get_config_var('Py_GIL_DISABLED'),
                       'requires free-threaded Python')
  def test_independent_streams_preserve_default_gil_policy(self):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    self.assertIsNone(sys.flags.gil)
    self.assertFalse(sys._is_gil_enabled())
    ready = Barrier(8)

    def round_trip(worker):
      ready.wait(10)
      for iteration in range(20):
        data = ('thread %d, iteration %d\n' % (worker, iteration)).encode() * 100
        encoder = brotli.Compressor(quality=2)
        encoded = encoder.process(data) + encoder.finish()
        decoder = brotli.Decompressor()
        self.assertEqual(decoder.process(encoded), data)
        self.assertTrue(decoder.is_finished())

    with ThreadPoolExecutor(max_workers=8) as pool:
      list(pool.map(round_trip, range(8)))
    self.assertFalse(sys._is_gil_enabled())

  @unittest.skipUnless(sys.version_info >= (3, 12), 'requires Python buffers')
  def test_compressor_rejects_reentrant_calls_from_buffer_exporter(self):
    compressor = brotli.Compressor()
    assert_raises = self.assertRaisesRegex

    class Input(object):
      def __buffer__(self, flags):
        with assert_raises(brotli.error, 'encoder concurrent access'):
          compressor.flush()
        return memoryview(b'brotli data')

    encoded = compressor.process(Input()) + compressor.finish()
    self.assertEqual(brotli.decompress(encoded), b'brotli data')

  @unittest.skipUnless(sys.version_info >= (3, 12), 'requires Python buffers')
  def test_decoder_state_is_unavailable_during_buffer_export(self):
    decoder = brotli.Decompressor()
    encoded = brotli.compress(b'brotli data')
    assert_raises = self.assertRaisesRegex

    class Input(object):
      def __buffer__(self, flags):
        with assert_raises(brotli.error, 'decoder concurrent access'):
          decoder.is_finished()
        with assert_raises(brotli.error, 'decoder concurrent access'):
          decoder.can_accept_more_data()
        return memoryview(encoded)

    self.assertEqual(decoder.process(Input()), b'brotli data')
    self.assertTrue(decoder.is_finished())
