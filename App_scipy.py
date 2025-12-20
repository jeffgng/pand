import numpy as np
import matplotlib.pyplot as plt
from scipy import optimize

def f(x,a,b,c,d):
    return a*x**3 + b*x**2 + c*x +d


x = np.linspace(-10, 10, 50)
y = 2*x**3 - x**2 + 3*x + 5 + np.random.normal(0, 100, size=len(x))
params, param_cov= optimize.curve_fit(f,x,y)


plt.scatter(x,y)
plt.plot(x,f(x, params[0], params[1], params[2], params[3]), c='green', lw=3)
plt.show()