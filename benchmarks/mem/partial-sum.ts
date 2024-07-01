import * as mem from "../../bril-ts/mem";

let size = 1000n;
let arr = mem.alloc<bigint>(size);

for (let i = 0n; i < size; i = i + 1n) {
	mem.store(mem.ptradd(arr, i), i); // arr[i] = i
}

let partialSums = mem.alloc<bigint>(size);
mem.store(mem.ptradd(partialSums, 0n), 0n); // partialSums[0] = 0
for (let i = 1n; i < size; i = i + 1n) {
	const prev = mem.load(mem.ptradd(partialSums, i - 1n)); // prev = partialSums[i - 1]
	mem.store(mem.ptradd(partialSums, i), prev + mem.load(mem.ptradd(arr, i))); // partialSums[i] = prev + arr[i]
}
for (let i = 0n; i < size; i = i + 1n) {
	console.log(mem.load(mem.ptradd(partialSums, i)));
}
mem.free(partialSums);
mem.free(arr);
