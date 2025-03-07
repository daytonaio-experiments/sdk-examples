import os
import urllib.request
import csv
from collections import defaultdict
import statistics
import math

# Step 1: Download and verify the dataset
print("Step 1: Downloading and verifying the dataset")
url = "https://www.timestored.com/data/sample/iris.csv"
file_path = "iris.csv"

# Download the file
try:
    urllib.request.urlretrieve(url, file_path)
    print(f"Successfully downloaded iris.csv from {url}")
    
    # Verify file existence and size
    if os.path.exists(file_path):
        file_size = os.path.getsize(file_path)
        print(f"File verified - Size: {file_size} bytes")
    else:
        print(f"Error: File not found at {file_path}")
        exit(1)
except Exception as e:
    print(f"Error downloading file: {e}")
    exit(1)

# Step 2: Examine the file structure
print("\nStep 2: Examining file structure")
row_count = 0
with open(file_path, 'r') as f:
    # Display first 5 lines
    print("First 5 lines of the file:")
    for i in range(5):
        line = f.readline().strip()
        print(f"  {line}")
    
    # Count total rows
    f.seek(0)
    row_count = sum(1 for line in f)
    
print(f"Total rows in file: {row_count}")

# Step 3: Load and parse the data
print("\nStep 3: Loading and parsing the data")
data = []
headers = []

with open(file_path, 'r') as f:
    reader = csv.reader(f)
    headers = next(reader)
    print(f"Headers: {headers}")
    
    for row in reader:
        if len(row) == len(headers):  # Ensure row is complete
            # Convert numeric values
            numeric_row = []
            for i, value in enumerate(row):
                if i < len(row) - 1:  # All but last column (species) are numeric
                    try:
                        numeric_row.append(float(value))
                    except ValueError:
                        print(f"Warning: Non-numeric value '{value}' found in row {len(data)+1}")
                        numeric_row.append(None)
                else:
                    numeric_row.append(value)  # Keep species as string
            data.append(numeric_row)

print(f"Successfully loaded {len(data)} data records")

# Step 4: Basic statistical analysis
print("\nStep 4: Basic statistical analysis")

# Separate by column
columns = [[] for _ in range(len(headers))]
for row in data:
    for i, value in enumerate(row):
        if i < len(headers) - 1 and value is not None:  # Numeric columns
            columns[i].append(value)
        elif i == len(headers) - 1:  # Species column
            columns[i].append(value)

# Calculate statistics for numeric columns
print("\nBasic Statistics for Numeric Features:")
print(f"{'Feature':<15} {'Min':>8} {'Max':>8} {'Mean':>8} {'Median':>8} {'StdDev':>8}")
print("-" * 60)

for i, col_data in enumerate(columns[:-1]):
    if len(col_data) > 0:
        min_val = min(col_data)
        max_val = max(col_data)
        mean_val = statistics.mean(col_data)
        median_val = statistics.median(col_data)
        stdev_val = statistics.stdev(col_data) if len(col_data) > 1 else 0
        
        print(f"{headers[i]:<15} {min_val:8.2f} {max_val:8.2f} {mean_val:8.2f} {median_val:8.2f} {stdev_val:8.2f}")

# Count by species
species_counts = defaultdict(int)
for species in columns[-1]:
    species_counts[species] += 1

print("\nSpecies Distribution:")
for species, count in species_counts.items():
    print(f"  {species}: {count} samples ({count/len(data)*100:.1f}%)")

# Step 5: Correlation analysis
print("\nStep 5: Correlation analysis")
print("\nFeature Correlations:")
print(f"{'Feature 1':<15} {'Feature 2':<15} {'Correlation':>10}")
print("-" * 45)

for i in range(len(columns) - 1):
    for j in range(i + 1, len(columns) - 1):
        x_values = columns[i]
        y_values = columns[j]
        
        # Calculate correlation coefficient
        x_mean = statistics.mean(x_values)
        y_mean = statistics.mean(y_values)
        
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values))
        denominator = math.sqrt(
            sum((x - x_mean)**2 for x in x_values) * 
            sum((y - y_mean)**2 for y in y_values)
        )
        
        correlation = numerator / denominator if denominator != 0 else 0
        print(f"{headers[i]:<15} {headers[j]:<15} {correlation:10.4f}")

# Step 6: Species-specific analysis
print("\nStep 6: Species-specific analysis")

# Group data by species
species_data = defaultdict(lambda: [[] for _ in range(len(headers) - 1)])
for row in data:
    species = row[-1]
    for i, value in enumerate(row[:-1]):
        if value is not None:
            species_data[species][i].append(value)

# Calculate mean values for each feature by species
print("\nFeature Means by Species:")
feature_header = "Feature"
species_headers = list(species_data.keys())
print(f"{feature_header:<15} " + " ".join(f"{s:>10}" for s in species_headers))
print("-" * (15 + 10 * len(species_headers)))

for i in range(len(headers) - 1):
    feature_name = headers[i]
    means = []
    for species in species_headers:
        feature_values = species_data[species][i]
        if feature_values:
            mean_val = statistics.mean(feature_values)
            means.append(f"{mean_val:10.2f}")
        else:
            means.append(f"{'N/A':>10}")
    
    print(f"{feature_name:<15} " + " ".join(means))

# Step 7: Feature value distribution by species
print("\nStep 7: Feature value ranges by species")
for i in range(len(headers) - 1):
    feature_name = headers[i]
    print(f"\nDistribution for {feature_name}:")
    print(f"{'Species':<15} {'Min':>8} {'25%':>8} {'Median':>8} {'75%':>8} {'Max':>8}")
    print("-" * 60)
    
    for species in species_headers:
        feature_values = sorted(species_data[species][i])
        if len(feature_values) > 0:
            min_val = feature_values[0]
            max_val = feature_values[-1]
            median_val = statistics.median(feature_values)
            
            # Calculate quartiles
            n = len(feature_values)
            q1_idx = n // 4
            q3_idx = 3 * n // 4
            q1 = feature_values[q1_idx]
            q3 = feature_values[q3_idx]
            
            print(f"{species:<15} {min_val:8.2f} {q1:8.2f} {median_val:8.2f} {q3:8.2f} {max_val:8.2f}")
        else:
            print(f"{species:<15} {'N/A':>8} {'N/A':>8} {'N/A':>8} {'N/A':>8} {'N/A':>8}")

# Step 8: Summary of findings
print("\nStep 8: Summary of key findings")
print("\nKey Insights from Iris Dataset Analysis:")
print("---------------------------------------")
print("1. Dataset composition:")
print(f"   - Total samples: {len(data)}")
for species, count in species_counts.items():
    print(f"   - {species}: {count} samples")

# Find most correlated features
correlations = []
for i in range(len(columns) - 1):
    for j in range(i + 1, len(columns) - 1):
        x_values = columns[i]
        y_values = columns[j]
        
        x_mean = statistics.mean(x_values)
        y_mean = statistics.mean(y_values)
        
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values))
        denominator = math.sqrt(
            sum((x - x_mean)**2 for x in x_values) * 
            sum((y - y_mean)**2 for y in y_values)
        )
        
        correlation = numerator / denominator if denominator != 0 else 0
        correlations.append((headers[i], headers[j], correlation))

# Sort by absolute correlation value
correlations.sort(key=lambda x: abs(x[2]), reverse=True)
top_correlation = correlations[0]
print(f"2. Strongest correlation: {top_correlation[0]} and {top_correlation[1]} (r = {top_correlation[2]:.4f})")

# Find most distinctive feature for species separation
feature_distinctiveness = []
for i in range(len(headers) - 1):
    feature_values_by_species = [species_data[species][i] for species in species_headers]
    
    # Calculate mean values
    means = [statistics.mean(values) for values in feature_values_by_species]
    
    # Calculate standard deviations
    stdevs = [statistics.stdev(values) if len(values) > 1 else 0 for values in feature_values_by_species]
    
    # Calculate a simple distinctiveness score
    # Higher score = more distinctive (higher difference between means relative to standard deviations)
    distinctiveness = 0
    for j in range(len(means)):
        for k in range(j + 1, len(means)):
            mean_diff = abs(means[j] - means[k])
            avg_stdev = (stdevs[j] + stdevs[k]) / 2 if (stdevs[j] + stdevs[k]) > 0 else 1
            distinctiveness += mean_diff / avg_stdev
    
    feature_distinctiveness.append((headers[i], distinctiveness))

# Sort by distinctiveness
feature_distinctiveness.sort(key=lambda x: x[1], reverse=True)
most_distinctive = feature_distinctiveness[0]
print(f"3. Most distinctive feature for species identification: {most_distinctive[0]}")

print("4. Feature characteristics by species:")
for species in species_headers:
    distinctive_features = []
    
    for i in range(len(headers) - 1):
        feature_name = headers[i]
        species_mean = statistics.mean(species_data[species][i])
        
        # Calculate mean for all other species combined
        other_values = []
        for other_species in species_headers:
            if other_species != species:
                other_values.extend(species_data[other_species][i])
        
        other_mean = statistics.mean(other_values)
        diff = species_mean - other_mean
        
        # Check if this feature is notably different for this species
        if abs(diff) > 0.5:  # Arbitrary threshold
            direction = "higher" if diff > 0 else "lower"
            distinctive_features.append(f"{feature_name} ({direction}, {abs(diff):.2f} diff)")
    
    print(f"   - {species} is characterized by: {', '.join(distinctive_features[:2])}")

print("\nAnalysis complete!")