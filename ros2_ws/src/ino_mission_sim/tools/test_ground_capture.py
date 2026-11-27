"""A stop command alone must not authorize a photograph on a rocking body."""
import math
import unittest
from ground_capture import CaptureStability


class StableCaptureTests(unittest.TestCase):
    def fill(self,state,count=25,rock=0.,jitter=False):
        for i in range(count):
            angle=rock*math.sin(i*.8)
            state.update(1.+i*.02,(0.,0.,9.8+(1. if i%2 else -1.) if jitter else 9.8),
                         (0.,.04*math.sin(i*math.pi/2) if jitter else 0.,0.),
                         (0.,math.sin(angle/2),0.,math.cos(angle/2)))

    def test_rest_must_be_sustained(self):
        state=CaptureStability();self.fill(state,count=8)
        self.assertFalse(state.stable(1.14))
        self.fill(state);self.assertTrue(state.stable(1.48))

    def test_rocking_restarts_wait_even_with_zero_command(self):
        state=CaptureStability();self.fill(state,rock=.02)
        self.assertFalse(state.stable(1.48))

    def test_missing_and_stale_imu_block_capture(self):
        state=CaptureStability();self.assertFalse(state.stable(1.))
        self.fill(state);self.assertFalse(state.stable(1.8))

    def test_contact_jitter_uses_quiet_acquisition_not_peak(self):
        state=CaptureStability();self.fill(state,rock=.0001,jitter=True)
        self.assertTrue(state.stable(1.48))
        self.assertTrue(state.quiet_at(1.48))
        self.assertFalse(state.quiet_at(1.46))
        self.assertFalse(state.quiet_at(1.49))


if __name__=='__main__':unittest.main()
