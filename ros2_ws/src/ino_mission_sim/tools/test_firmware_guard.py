"""Execute native C++ decisions; these are synthetic traces, not Gazebo proof."""
import tempfile,unittest
from pathlib import Path
from firmware_trace import run,ROOT

class GuardTests(unittest.TestCase):
    def setUp(self):
        if not (ROOT/'firmware/sil/build/guarded/legacy_sil').exists():self.skipTest('Build guarded profile first')
        self.temp=tempfile.TemporaryDirectory(prefix='cansat-guard-test-');self.addCleanup(self.temp.cleanup)
    def trace(self,**kwargs):return run('guarded',Path(self.temp.name),**kwargs)
    def test_stationary_before_release_never_arms(self):
        result,rows=self.trace(hold_only=True,duration=40.)
        self.assertIsNone(result['first_guard_landed_s']);self.assertTrue(all(r['guard_stage']==0 and r['action']==0 and r['separation']==0 for r in rows))
    def test_landing_requires_descent_and_two_seconds_stability(self):
        result,_=self.trace();self.assertGreaterEqual(result['first_guard_landed_s'],15.9);self.assertFalse(result['premature_separation'])
    def test_missing_gnss_stops_then_recovers(self):
        result,rows=self.trace(sensors={'gnss':{'blackouts':[[28.,35.]]}})
        missing=[r for r in rows if r['guard_stage']==2 and r['health_mask']&2==0]
        self.assertTrue(missing);self.assertTrue(all(r['action']==0 for r in missing));self.assertTrue(any(r['time_s']>35.5 and r['action'] for r in rows))
    def test_aged_camera_prevents_drive(self):
        result,rows=self.trace(sensors={'camera':{'delay_s':1.}})
        self.assertIsNotNone(result['first_guard_landed_s']);self.assertTrue(all(r['action']==0 for r in rows))
    def test_goal_stop_stays_latched(self):
        # Fixed synthetic GNSS coincides with the goal after ground confirmation.
        result,rows=self.trace(sensors={'gnss':{'bias':[0.,11.0946252]}})
        goal=[r for r in rows if r['phase']==6];self.assertTrue(goal)
        self.assertTrue(all(r['action']==0 for r in rows if r['time_s']>=goal[0]['time_s']))
