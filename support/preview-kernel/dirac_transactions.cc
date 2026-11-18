// Only the new scaled-distribution paths; keep the production bridge budgets.
#include "giac_port.h"
#include "giac_memory.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>

namespace {
unsigned polls,threshold;
int cancel(){ return ++polls>=threshold; }
void require(bool okay,const char *message){
  if (!okay){ std::fprintf(stderr,"FAIL Dirac recovery: %s\n",message); std::_Exit(1); }
}
int evaluate(const char *input,const char *expected){
  char result[256],error[192];
  int status=giac_port_eval(input,result,sizeof result,error,sizeof error);
  if (status==GIAC_PORT_OK){
    if (std::strcmp(result,expected)){
      std::fprintf(stderr,"%s returned [%s], expected [%s]\n",input,result,expected);
      std::_Exit(1);
    }
  } else require(!*result && *error,"failed operation published output");
  return status;
}
void state(size_t baseline){
  require(giac_memory::used()==baseline,"operation retained allocations");
  require(evaluate("Ans","42")==GIAC_PORT_OK,"Ans changed after failure");
  require(evaluate("a","42")==GIAC_PORT_OK,"variable changed after failure");
  require(giac_memory::used()==baseline,"state checks changed live charge");
}
void sweep(const char *name,const char *operation,const char *expected){
  require(evaluate(operation,expected)==GIAC_PORT_OK,"warm operation");
  require(evaluate("a:=42","42")==GIAC_PORT_OK,"initialize state");
  size_t baseline=giac_memory::used();
  size_t failures=0;
  for (;failures<4096;++failures){
    int status;
    {
      giac_memory::Scope inject(SIZE_MAX,0);
      inject.fail_after(failures);
      status=evaluate(operation,expected);
    }
    if (status==GIAC_PORT_OK) break;
    require(status==GIAC_PORT_OOM,"allocation failure returned wrong status");
    state(baseline);
  }
  require(failures<4096,"allocation sweep did not finish");
  require(evaluate("a:=42","42")==GIAC_PORT_OK,"restore state");
  baseline=giac_memory::used();
  polls=0; threshold=~0u;
  giac_port_set_cancel_poll(cancel);
  require(evaluate(operation,expected)==GIAC_PORT_OK,"count cancellation polls");
  giac_port_set_cancel_poll(nullptr);
  unsigned total=polls;
  const unsigned points[]={1,total/2,total-1};
  require(total>=4,"too few cooperative checkpoints");
  for (unsigned i=0;i<3;++i){
    require(evaluate("a:=42","42")==GIAC_PORT_OK,"restore before cancellation");
    baseline=giac_memory::used();
    polls=0; threshold=points[i];
    giac_port_set_cancel_poll(cancel);
    int status=evaluate(operation,expected);
    giac_port_set_cancel_poll(nullptr);
    require(status==GIAC_PORT_CANCELLED,"operation ignored cancellation");
    state(baseline);
    require(evaluate("7*8+1","57")==GIAC_PORT_OK,"arithmetic after cancellation");
  }
  std::printf("{\"case\":\"%s\",\"injected_failures\":%zu,\"cancellations\":3,\"polls\":%u}\n",name,failures,total);
  std::fflush(stdout);
}
}
extern "C" int khicas_cli_main(){
  char error[192];
  require(giac_port_init(error,sizeof error)==GIAC_PORT_OK,"initialize bridge");
  sweep("linear delta","a:=normal(integrate(diff(Heaviside(2*x),x),x,-1,1))",
#ifdef BASELINE_RECOVERY
        "2"); // The old mathematical error is intentional in this control.
#else
        "1");
#endif
  sweep("polynomial delta derivative","a:=normal(integrate((x^2+1)*diff(Heaviside(-2*x+1),x,2),x,-1,1))",
#ifdef BASELINE_RECOVERY
        "-4");
#else
        "1");
#endif
  giac_port_shutdown();
  std::puts("{\"complete\":true}");
  return 0;
}
