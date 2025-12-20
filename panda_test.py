import numpy as np
import matplotlib.pyplot as plt
from scipy import optimize
import pandas as pd
data = pd.read_excel("titanic3.xls")
print(data.shape)
"""print(data.head)
print(data.columns)"""
print(data.drop(['name', 'sibsp','parch', 'ticket', 'fare', 'ticket', 'embarked', 'boat', 'body', 'home.dest', 'cabin'], axis=1))
data.describe()
data= data.dropna(subset=['pclass'])
print(data.shape)
count= data['pclass'].value_counts().plot.bar()
print(count)
