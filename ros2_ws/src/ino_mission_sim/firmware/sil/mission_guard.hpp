#pragma once
// Host/MCU independent decision logic. altitude_m must be ground-referenced.
// Thresholds are provisional test parameters, not flight-qualified values.
#include <algorithm>
#include <cmath>
#include <deque>
#include <utility>
namespace cansat_sim {
struct GuardInput {
  unsigned long now=0;
  double altitude=0,acceleration=0;
  unsigned valid=31;
  long barometer_ms=-1,gnss_ms=-1,imu_ms=-1,heading_ms=-1,camera_ms=-1;
};
class MissionGuard {
 public:
  enum Stage { Waiting=0, Descending=1, Landed=2 };
  Stage stage=Waiting;
  // Hard freshness limits also protect against an adapter incorrectly retaining
  // validity after receipt has stopped. Times are acquisition times, not delivery.
  unsigned healthy(const GuardInput& in) const {
    const long stamps[]={in.barometer_ms,in.gnss_ms,in.imu_ms,in.heading_ms,in.camera_ms};
    const long limits[]={500,2500,300,700,700}; unsigned result=in.valid;
    for(unsigned i=0;i<5;++i)
      if(stamps[i]<0 || stamps[i]>long(in.now) || long(in.now)-stamps[i]>limits[i])result&=~(1u<<i);
    return result;
  }
  void update(const GuardInput& in) {
    if(stage==Landed)return;
    const unsigned mask=healthy(in);
    if((mask&5)!=5 || !std::isfinite(in.altitude) || !std::isfinite(in.acceleration)) {
      history.clear();descending_since=-1;return;
    }
    if(in.barometer_ms==last_sample)return;
    last_sample=in.barometer_ms;
    maximum=std::max(maximum,in.altitude);
    history.push_back({in.barometer_ms,in.altitude});
    while(history.size()>1 && history[1].first<=in.barometer_ms-2000)history.pop_front();
    if(history.size()<2)return;
    const double span=(history.back().first-history.front().first)/1000.;
    if(span<=0)return;
    const double rate=(history.back().second-history.front().second)/span;
    if(stage==Waiting) {
      if(maximum-in.altitude>=1. && rate<-.8) {
        if(descending_since<0)descending_since=in.barometer_ms;
        if(in.barometer_ms-descending_since>=500){stage=Descending;history.clear();}
      } else descending_since=-1;
    } else if(span>=1.9 && in.altitude<=2. && std::abs(rate)<.15 && in.acceleration<.8) {
      double low=in.altitude,high=in.altitude;
      for(auto sample:history){low=std::min(low,sample.second);high=std::max(high,sample.second);}
      if(high-low<=.25 && maximum-in.altitude>=3.)stage=Landed;
    }
  }
 private:
  double maximum=-1e9;
  long last_sample=-1,descending_since=-1;
  std::deque<std::pair<long,double>> history;
};
}
