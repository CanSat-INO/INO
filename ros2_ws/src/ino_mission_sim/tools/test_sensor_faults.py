import unittest
import numpy as np
from sensor_faults import Channel

class SensorFaultTests(unittest.TestCase):
    def test_delay_retains_acquisition_stamp(self):
        c=Channel('gnss',dict(delay_s=.4),27);c.push(1.,[3.,4.])
        self.assertFalse(c.read(1.39)['valid']);r=c.read(1.4)
        self.assertEqual(r['stamp_s'],1.);self.assertAlmostEqual(r['age_s'],.4);np.testing.assert_equal(r['value'],[3.,4.])
    def test_dropout_expires_old_value_and_recovers(self):
        c=Channel('barometer',dict(blackouts=[[1.,2.]],max_age_s=.5),27);c.push(.9,[4.]);c.push(1.2,[0.])
        self.assertFalse(c.read(1.5)['valid']);self.assertEqual(c.read(1.5)['value'][0],4.)
        c.push(2.,[0.]);self.assertTrue(c.read(2.)['valid'])
    def test_seed_reproduces_noise_and_jitter(self):
        cfg=dict(noise_std=[.5,.2],jitter_s=.1,drop_probability=.2)
        a=Channel('gnss',cfg,31);b=Channel('gnss',cfg,31)
        for i in range(20):a.push(i*.2,[0.,0.]);b.push(i*.2,[0.,0.])
        for t in [1.,2.,3.,4.]:
            x,y=a.read(t),b.read(t);self.assertEqual(x['stamp_s'],y['stamp_s']);np.testing.assert_equal(x['value'],y['value'])
    def test_out_of_order_never_rewinds_observation(self):
        c=Channel('heading',dict(jitter_s=1.,period_s=0.),27)
        for i in range(30):c.push(i*.05,[i])
        last=-1.
        for t in np.arange(0,3,.02):
            r=c.read(t)
            if r['stamp_s'] is not None:self.assertGreaterEqual(r['stamp_s'],last);last=r['stamp_s']
    def test_image_payload_is_not_rewritten(self):
        c=Channel('camera',dict(delay_s=.2),27);c.push(1.,b'pixels');self.assertEqual(c.read(1.2)['value'],b'pixels')
    def test_invalid_config_rejected(self):
        for cfg in [dict(delay_s=-1),dict(drop_probability=2),dict(noise_std=-1),dict(blackouts=[[2.,1.]])]:
            with self.assertRaises(ValueError):Channel('gnss',cfg,27)
