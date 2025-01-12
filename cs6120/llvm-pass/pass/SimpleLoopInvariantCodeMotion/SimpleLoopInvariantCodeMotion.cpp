#include "llvm/ADT/ArrayRef.h"
#include "llvm/ADT/StringRef.h"
#include "llvm/IR/PassManager.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Passes/PassPlugin.h"
#include "llvm/Support/Compiler.h"

#define DEBUG_TYPE "slicm"

using namespace llvm;

namespace {

constexpr char PassName[] = DEBUG_TYPE;
constexpr char PluginName[] = "Simple Loop Invariant Code Motion";

class SimpleLoopInvariantCodeMotionPass
    : public PassInfoMixin<SimpleLoopInvariantCodeMotionPass> {
public:
  PreservedAnalyses run(Function &F, FunctionAnalysisManager &FAM) {
    return PreservedAnalyses::all();
  }
};

} // namespace

extern "C" LLVM_ATTRIBUTE_WEAK ::llvm::PassPluginLibraryInfo
llvmGetPassPluginInfo() {
  return {LLVM_PLUGIN_API_VERSION, PluginName, LLVM_VERSION_STRING,
          [](PassBuilder &PB) {
            PB.registerPipelineParsingCallback(
                [](StringRef Name, FunctionPassManager &FPM,
                   ArrayRef<PassBuilder::PipelineElement>) {
                  if (!Name.compare(PassName)) {
                    FPM.addPass(SimpleLoopInvariantCodeMotionPass());
                    return true;
                  }
                  return false;
                });
          }};
}
