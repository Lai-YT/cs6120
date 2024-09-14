# llvm-pass

Built with LLVM-17.

Build:

```shell
mkdir build
cd build
LLVM_DIR=$(llvm-config-17 --cmakedir) cmake ..
make
cd ..
```

Run:

```shell
clang-17 -fpass-plugin="build/pass/<pass>.so" <source>
```
