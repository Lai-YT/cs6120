#include "llvm/Pass.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Passes/PassPlugin.h"
#include "llvm/Support/raw_ostream.h"

using namespace llvm;

namespace {

struct TrivialConstantFoldingPass
    : public PassInfoMixin<TrivialConstantFoldingPass> {
  PreservedAnalyses run(Module &M, ModuleAnalysisManager &AM) {
    for (auto &F : M) {
      errs() << "I saw a function called " << F.getName() << "!\n";
    }
    return PreservedAnalyses::all();
  }
};

} // namespace

extern "C" LLVM_ATTRIBUTE_WEAK ::llvm::PassPluginLibraryInfo
llvmGetPassPluginInfo() {
  return {.APIVersion = LLVM_PLUGIN_API_VERSION,
          .PluginName = "Trivial Constant Folding pass",
          .PluginVersion = "v0.1",
          .RegisterPassBuilderCallbacks = [](PassBuilder &PB) {
            PB.registerPipelineStartEPCallback(
                [](ModulePassManager &MPM, OptimizationLevel Level) {
                  MPM.addPass(TrivialConstantFoldingPass());
                });
          }};
}
