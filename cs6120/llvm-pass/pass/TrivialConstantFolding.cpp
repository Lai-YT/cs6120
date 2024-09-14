#include "llvm/IR/Constants.h"
#include "llvm/IR/InstrTypes.h"
#include "llvm/IR/Instruction.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/Module.h"
#include "llvm/IR/PassManager.h"
#include "llvm/IR/Value.h"
#include "llvm/Pass.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Passes/PassPlugin.h"
#include "llvm/Support/raw_ostream.h"

using namespace llvm;

namespace {

struct TrivialConstantFoldingPass
    : public PassInfoMixin<TrivialConstantFoldingPass> {
  PreservedAnalyses run(Module &M, ModuleAnalysisManager &AM) {
    bool Changed = false;
    for (auto &F : M) {
      for (auto &BB : F) {
        for (auto &I : BB) {
          if (auto *BOP = dyn_cast<BinaryOperator>(&I)) {
            auto *LHSC = dyn_cast<ConstantInt>(BOP->getOperand(0));
            auto *RHSC = dyn_cast<ConstantInt>(BOP->getOperand(1));

            if (LHSC && RHSC) {
              errs() << "Warning: It's unusual that Clang not constant fold "
                        "this.\n";
              continue;
            }

            Value *Result = nullptr;
            if (LHSC) {
              if (LHSC->isZero()) {
                switch (BOP->getOpcode()) {
                case Instruction::Add:
                  Result = BOP->getOperand(1);
                  break;
                case Instruction::Mul:
                  Result = LHSC; // 0
                  break;
                default:
                  break;
                }
              } else if (LHSC->isOne()) {
                switch (BOP->getOpcode()) {
                case Instruction::Mul:
                  Result = RHSC;
                  break;
                default:
                  break;
                }
              }
            } else if (RHSC) {
              if (RHSC->isZero()) {
                switch (BOP->getOpcode()) {
                case Instruction::Add:
                case Instruction::Sub:
                  Result = LHSC;
                  break;
                case Instruction::Mul:
                  Result = RHSC; // 0
                  break;
                default:
                  break;
                }
              } else if (RHSC->isOne()) {
                switch (BOP->getOpcode()) {
                case Instruction::Mul:
                case Instruction::SDiv:
                  Result = LHSC;
                  break;
                default:
                  break;
                }
              }
            }
            if (Result) {
              BOP->replaceAllUsesWith(Result);
              Changed = true;
            }
          }
        }
      }
    }
    return Changed ? PreservedAnalyses::none() : PreservedAnalyses::all();
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
