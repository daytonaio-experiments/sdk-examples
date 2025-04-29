import os

def flattenNestedList(input):
  flat_list = []
  for i in range(len(input)):
      if input[i] != []:
            for j in range(len(input[i])):
              flat_list.append(input[i][j])
  return flat_list