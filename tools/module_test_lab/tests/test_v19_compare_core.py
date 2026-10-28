from __future__ import annotations
import csv
from pathlib import Path
import pytest
from v19_compare_core import read_log, compare_logs, report, save_result


def write(path, rows, head=('time_s','distance_m')):
    with open(path,'w',newline='',encoding='utf-8') as f:
        writer=csv.writer(f);writer.writerow(head);writer.writerows(rows)


def test_interpolation_and_metrics(tmp_path):
    a,b=tmp_path/'actual.csv',tmp_path/'ref.csv'
    write(a,[(0,1),(0.5,2.5),(1,4),(1.5,5.5),(2,7)])
    write(b,[(0,1),(1,3),(2,5)])
    got=compare_logs(read_log(a),read_log(b),'distance_m','distance_m',unit_confirmed=True)
    assert got.matched==5 and got.coverage_fraction==1
    assert got.bias==pytest.approx(1)
    assert got.mae==pytest.approx(1)
    assert got.rmse==pytest.approx(((0+0.5**2+1**2+1.5**2+2**2)/5)**.5)
    assert report(got)['validation']=='not_hardware_validation'
    assert got.points[1].reference==pytest.approx(2)


def test_shift_and_overlap(tmp_path):
    a,b=tmp_path/'a.csv',tmp_path/'b.csv'
    write(a,[(0,10),(1,20),(2,30),(3,40)])
    write(b,[(0,15),(1,25),(2,35)])
    got=compare_logs(read_log(a),read_log(b),'distance_m','distance_m',unit_confirmed=True,time_shift_s=1)
    assert got.matched==3
    assert got.coverage_fraction==.75
    assert [p.time_s for p in got.points]==[1,2,3]
    with pytest.raises(ValueError,match='重なって'):
        compare_logs(read_log(a),read_log(b),'distance_m','distance_m',unit_confirmed=True,time_shift_s=99)


def test_requires_confirmation_time_and_valid_signal(tmp_path):
    a=tmp_path/'a.csv';b=tmp_path/'b.csv'
    write(a,[(0,1),(1,2)])
    write(b,[(0,1),(1,2)])
    with pytest.raises(ValueError,match='単位'):
        compare_logs(read_log(a),read_log(b),'distance_m','distance_m',unit_confirmed=False)
    with pytest.raises(ValueError,match='信号列'):
        compare_logs(read_log(a),read_log(b),'not_a_signal','distance_m',unit_confirmed=True)
    write(a,[(0,1),(0,2)])
    with pytest.raises(ValueError,match='時刻'):
        read_log(a)
    write(a,[(1,2),(2,3)], head=('unknown_time','distance_m'))
    with pytest.raises(ValueError,match='時間列'):
        read_log(a)


def test_save_and_sample(tmp_path):
    root=Path(__file__).resolve().parents[1]
    a=read_log(root/'v19_samples/example_measured.csv')
    b=read_log(root/'v19_samples/example_v17_reference.csv')
    got=compare_logs(a,b,'distance_m','distance_m',unit_confirmed=True)
    assert got.matched>=40
    assert 0 < got.mae < 1
    save_result(got,tmp_path/'out.csv','csv')
    save_result(got,tmp_path/'out.json','json')
    assert (tmp_path/'out.csv').stat().st_size>50
    assert 'not_hardware_validation' in (tmp_path/'out.json').read_text()


def test_empty_overlap_and_missing(tmp_path):
    a=tmp_path/'a.csv'; b=tmp_path/'b.csv'
    write(a,[(0,''),(1,2),(2,3),(3,4)])
    write(b,[(0,2),(3,5)])
    got=compare_logs(read_log(a),read_log(b),'distance_m','distance_m',unit_confirmed=True)
    assert got.matched==3 and got.measured_valid==3
    write(a,[(0,''),(1,''),(2,3)])
    with pytest.raises(ValueError,match='2件以上'):
        compare_logs(read_log(a),read_log(b),'distance_m','distance_m',unit_confirmed=True)
