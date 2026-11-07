# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import subprocess,tempfile,shutil,json
ROOT=Path(__file__).resolve().parents[1];BASE='0bbac29e2a2f37d9f0dd149fb78f65da82509a83';P='media/codec2/sfplugin/CCodecBufferChannel.cpp'
def body(s):
 a=s.index('void CCodecBufferChannel::feedInputBufferIfAvailable()');return s[a:s.index('\n}\n',a)+3]
pre=r'''
#include <algorithm>
#include <chrono>
#include <mutex>
#include <cstdint>
#include <iostream>
#define ALOGV(...) ((void)0)
constexpr uint64_t kPipelinePausedTimeoutMs=500;
static uint64_t clockMs;
struct MockClock {
 using rep=int64_t;using period=std::milli;using duration=std::chrono::milliseconds;using time_point=std::chrono::time_point<MockClock>;
 static time_point now(){return time_point(duration(clockMs));}
};
struct PipelineWatcher{using Clock=MockClock;};
struct Sync{bool running=true;};
struct QueueGuard{Sync&s;QueueGuard(Sync&v):s(v){};bool isRunning(){return s.running;}};
class CCodecBufferChannel{public:
 Sync mSync;const char*mName="test";bool mIsHWDecoder=true;uint64_t mLastInputBufferAvailableTs=0,mLastDummyWorkTs=0;
 std::mutex mTsLock;int queued=0,fed=0;bool inputAvailable=false;
 void queueDummyWork(){queued++;}
 void feedInputBufferIfAvailableInternal(){fed++;if(inputAvailable)mLastInputBufferAvailableTs=clockMs;}
 void feedInputBufferIfAvailable();
};
'''
post=r'''
int main(){
 int checks=0,failures=0;auto check=[&](bool ok){checks++;if(!ok)failures++;};
 clockMs=1000;CCodecBufferChannel channel;
 // Model repeated completion callbacks from a vendor that returns C2_OK
 // for the empty work. No real input buffer becomes available.
 for(int i=0;i<1000;i++)channel.feedInputBufferIfAvailable();
 const int burstQueued=channel.queued;
 check(channel.queued==1);check(channel.fed==1000);
 clockMs=1500;channel.feedInputBufferIfAvailable();check(channel.queued==1);
 clockMs=1501;channel.feedInputBufferIfAvailable();check(channel.queued==2);
 clockMs=2000;channel.inputAvailable=true;channel.feedInputBufferIfAvailable();check(channel.queued==2);
 channel.inputAvailable=false;clockMs=2400;channel.feedInputBufferIfAvailable();check(channel.queued==2);
 clockMs=2501;channel.feedInputBufferIfAvailable();check(channel.queued==3);
 CCodecBufferChannel stopped;stopped.mSync.running=false;stopped.feedInputBufferIfAvailable();check(stopped.queued==0&&stopped.fed==0);
 CCodecBufferChannel software;software.mIsHWDecoder=false;software.feedInputBufferIfAvailable();check(software.queued==0&&software.fed==1);
 CCodecBufferChannel recent;recent.mLastInputBufferAvailableTs=clockMs;recent.feedInputBufferIfAvailable();check(recent.queued==0);
 std::cout<<"{\"checks\":"<<checks<<",\"failures\":"<<failures<<",\"callbacks_in_burst\":1000,\"initial_burst_dummy_work\":"<<burstQueued<<"}";return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='ccodec-wakeup-') as tmp:
 H=Path(tmp);cxx=shutil.which('g++');assert cxx;results={}
 for variant in ['original','candidate']:
  s=subprocess.run(['git','-C',str(ROOT),'show',BASE+':'+P],capture_output=True,text=True,encoding='utf-8',check=True).stdout if variant=='original' else (ROOT/P).read_text()
  f=H/(variant+'.cpp');f.write_text(pre+body(s)+post);exe=H/(variant+'.exe')
  r=subprocess.run([cxx,'-std=c++17','-O2','-Wall','-Wextra','-Werror','-static',str(f),'-o',str(exe)],capture_output=True,text=True);assert r.returncode==0,r.stderr
  r=subprocess.run([str(exe)],capture_output=True,text=True,check=True);results[variant]=json.loads(r.stdout)
 assert results['candidate']['failures']==0 and results['original']['failures']>0
 results['scope']='Actual production feed function with a deterministic clock, modeled input/queue callbacks and a real mutex; no Android component or device binary was built.'
 print(json.dumps(results,indent=2))
