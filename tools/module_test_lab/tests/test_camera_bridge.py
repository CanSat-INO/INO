import csv
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from camera_bridge import ros_environment,list_results,results_csv,load_config,PACKAGE


class CameraBridgeTests(unittest.TestCase):
    def test_venv_not_inherited_by_ros(self):
        with patch.dict(os.environ,{'VIRTUAL_ENV':'/tmp/test-venv','PYTHONHOME':'/tmp/test-venv','PATH':'/tmp/test-venv/bin:/usr/bin:/bin'}):
            env=ros_environment()
        self.assertNotIn('VIRTUAL_ENV',env);self.assertNotIn('PYTHONHOME',env)
        self.assertEqual(env['PATH'],'/usr/bin:/bin')

    def test_result_distinguishes_completed_from_tracking(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'logs'/'test';folder.mkdir(parents=True)
            result={'completed':True,'mode':'sequential','matched_samples':3,'tracking_valid_fraction':1,'final_pose_age_s':0,'image_pairs':4}
            (folder/'result.json').write_text(json.dumps(result))
            rows=list_results(root)
            self.assertIn('要確認',rows[0]['status'])
            result['matched_samples']=20;(folder/'result.json').write_text(json.dumps(result))
            self.assertIn('目安を満たす',list_results(root)[0]['status'])
            result['completed']=False;(folder/'result.json').write_text(json.dumps(result))
            self.assertEqual(list_results(root)[0]['status'],'未完了')

    def test_incomplete_json_and_external_symlink_are_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);logs=root/'logs';logs.mkdir();broken=logs/'broken';broken.mkdir();(broken/'result.json').write_text('{')
            outside=root/'outside';outside.mkdir();(outside/'result.json').write_text('{"completed":true}')
            (logs/'link').symlink_to(outside,target_is_directory=True)
            self.assertEqual(list_results(root),[])

    def test_csv_has_no_local_folder_path(self):
        rows=[{'name':'sample','mode':'continuous','status':'未完了','pairs':2,'samples':0,'fraction':0,'rmse_m':None,'moving_captures':1,'stereo_skew_s':0,'folder':'/private/path'}]
        raw=results_csv(rows);self.assertNotIn('/private',raw)
        self.assertEqual(list(csv.DictReader(io.StringIO(raw)))[0]['pairs'],'2')

    @unittest.skipUnless(PACKAGE.exists() and Path('/usr/bin/python3').exists(),'camera package unavailable')
    def test_config_helper_works_without_ros_in_test_lab_python(self):
        config=load_config()
        self.assertEqual(config['camera']['width'],640)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'invalid.json';config['camera']['baseline_m']=-1;path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):load_config(path)

if __name__=='__main__':unittest.main()
