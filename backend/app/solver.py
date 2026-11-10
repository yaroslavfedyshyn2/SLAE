
import numpy as np
 
 
class SolverCancelled(Exception):
    """Користувач скасував задачу."""
 
 
class SingularMatrix(Exception):
    """Матриця вироджена: єдиного розв'язку немає."""
 
 
def swap_rows(M, i, j):
    if i != j:
        M[[i, j]] = M[[j, i]]
 
 
def solve_gauss(a, b, on_progress=None, should_cancel=None, atol=1e-7, block=256):
    """
    Розв'язує A·x = b методом Гаусса з вибором головного елемента.
 
    on_progress(row, n) - викликається приблизно кожен 1% рядків
    should_cancel()     - якщо повертає True, кидаємо SolverCancelled
    Повертає numpy-масив x.
    """
    A = np.array(a, dtype=np.float64)  
    B = np.array(b, dtype=np.float64)
 
    if A.ndim != 2:
        raise ValueError("Matrix A should have 2 dimensions")
    n, m = A.shape
    if n != m:
        raise ValueError("Matrix A should be square NxN")
    if B.shape != (n,):
        raise ValueError("Vector b should have the same length as matrix A")
 
    step = max(1, n // 100)
 
    # ---- Прямий хід ----
    for k in range(n):
        if should_cancel is not None and should_cancel():
            raise SolverCancelled()
 
        pivot = int(np.argmax(np.abs(A[k:, k]))) + k
        if abs(A[pivot, k]) < atol:
            raise SingularMatrix()
 
        if pivot != k:
            swap_rows(A, k, pivot)
            B[k], B[pivot] = B[pivot], B[k]
 
        pivot_val = A[k, k]
        A[k, k:] /= pivot_val           # ліва частина рядка вже нулі
        B[k] /= pivot_val
 
        factors = A[k + 1:, k].copy()   # копія: стовпець k ми зараз занулимо
        row_k = A[k, k:]
        for s in range(0, len(factors), block):
            f = factors[s:s + block]
            lo = k + 1 + s
            hi = lo + len(f)
            A[lo:hi, k:] -= f[:, None] * row_k
            B[lo:hi] -= f * B[k]
 
        if on_progress is not None and (k % step == 0 or k == n - 1):
            on_progress(k + 1, n)
 

    x = np.zeros(n)
    for i in range(n - 1, -1, -1):
        x[i] = B[i] - np.dot(A[i, i + 1:], x[i + 1:])
 
    return x