#define khicas_cli_main dirac_recovery_main
#include "dirac_transactions.cc"
#undef khicas_cli_main
extern "C" {
#define main dirac_input_main
#include "cas_cli.c"
#undef main
}
extern "C" int khicas_cli_main(){
  int first=std::getchar();
  if (first==':') return dirac_recovery_main();
  if (first!=EOF) std::ungetc(first,stdin);
  return dirac_input_main();
}
