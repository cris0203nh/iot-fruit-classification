#include "../firmware/agroscan_scale/ScaleCore.h"
#include <cassert>
#include <cstring>
#include <iostream>
#include <limits>
using namespace agroscan;
static void fill(ScaleCore& s,int raw,uint32_t& t) {for(size_t i=0;i<WINDOW;++i){t+=100;s.add(raw,t);}}
static void status(ScaleCore& s,uint32_t t,const char* expected){assert(!strcmp(s.reading(t).status,expected));}
int main(){
 unsigned tests=0;
 {ScaleCore s;status(s,0,"sensor_unavailable");++tests;}
 {ScaleCore s;uint32_t t=0;fill(s,100000,t);status(s,t,"uncalibrated");assert(!s.reading(t).valid);++tests;}
 {ScaleCore s;uint32_t t=0;assert(!s.tare(t));fill(s,100000,t);assert(!s.calibrate(500,t));++tests;}
 {ScaleCore s;uint32_t t=0;fill(s,100000,t);assert(s.tare(t));fill(s,150000,t);assert(s.calibrate(500,t));assert(s.calibration().counts_per_gram==100);fill(s,125000,t);assert(s.reading(t).stable);assert(s.reading(t).weight_g==250);++tests;}
 {ScaleCore s;uint32_t t=0;fill(s,100000,t);assert(s.tare(t));fill(s,50000,t);assert(s.calibrate(500,t));fill(s,75000,t);assert(s.reading(t).weight_g==250);++tests;}
 {ScaleCore s;uint32_t t=0;fill(s,100000,t);assert(s.tare(t));fill(s,100000,t);assert(!s.calibrate(500,t));assert(!s.calibrate(0,t));assert(!s.calibrate(-1,t));assert(!s.calibrate(5001,t));assert(!s.calibrate(std::numeric_limits<double>::quiet_NaN(),t));++tests;}
 {ScaleCore s;Calibration c;c.offset=100000;c.counts_per_gram=100;c.revision=1;s.restore(c);uint32_t t=0;fill(s,100000,t);status(s,t,"zero_required");assert(s.tare(t));s.add(100000,t+=100);status(s,t,"warming_up");fill(s,100000,t);status(s,t,"stable");++tests;}
 {ScaleCore s;Calibration c;c.offset=100000;c.counts_per_gram=100;c.revision=1;s.restore(c);uint32_t t=0;fill(s,100000,t);s.tare(t);fill(s,99900,t);assert(s.reading(t).weight_g==0);fill(s,99000,t);status(s,t,"out_of_range");fill(s,600100,t);status(s,t,"out_of_range");++tests;}
 {ScaleCore s;Calibration c;c.offset=100000;c.counts_per_gram=100;c.revision=1;s.restore(c);uint32_t t=0;fill(s,100000,t);s.tare(t);for(size_t i=0;i<WINDOW;++i)s.add(i%2?125400:124600,t+=100);status(s,t,"unstable");assert(!s.reading(t).stable);++tests;}
 {ScaleCore s;uint32_t t=0;fill(s,100000,t);assert(s.rawStable(t));t+=TIMEOUT_MS+1;status(s,t,"sensor_unavailable");assert(!s.tare(t));s.add(100000,t);assert(!s.rawStable(t));++tests;}
 {ScaleCore s;uint32_t t=0;fill(s,100000,t);s.fault();status(s,t,"sensor_unavailable");fill(s,100000,t);assert(s.rawStable(t));++tests;}
 {ScaleCore s;uint32_t t=0;fill(s,100000,t);assert(!s.add(8388607,t));status(s,t,"sensor_unavailable");assert(!s.add(-8388608,t));++tests;}
 {ScaleCore s;Calibration c;c.offset=0;c.counts_per_gram=0;c.revision=1;s.restore(c);uint32_t t=0;fill(s,100000,t);status(s,t,"uncalibrated");c.counts_per_gram=std::numeric_limits<double>::infinity();s.restore(c);fill(s,100000,t);status(s,t,"uncalibrated");++tests;}
 {ScaleCore s;uint32_t t=UINT32_MAX-500;fill(s,100000,t);assert(s.rawStable(t));assert(s.fresh(t+100));assert(!s.fresh(t+TIMEOUT_MS+1));++tests;}
 {ScaleCore s;uint32_t t=0;fill(s,100000,t);s.add(100000,t+=MAX_GAP_MS+1);assert(!s.rawStable(t));++tests;}
 {ScaleCore s;uint32_t t=0;for(size_t i=0;i<WINDOW;++i)s.add(i%2?100400:99600,t+=100);assert(!s.tare(t));++tests;}
 std::cout<<tests<<" grupos de pruebas ScaleCore aprobados\n";
}
