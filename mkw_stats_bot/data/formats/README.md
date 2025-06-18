# 📐 OCR Format Mappings

This folder stores OCR region mappings for different table layouts.

## 🎯 Purpose

Each format file contains pixel coordinates that tell the OCR where to look for player names and scores in different table layouts.

## 📁 File Structure

```
formats/
├── format_1.json     # Standard side-by-side table
├── format_2.json     # Stacked team table
├── format_3.json     # Detailed score table
└── README.md         # This file
```

## 🖱️ Creating Format Mappings

### 1. Use Region Selector

```bash
# Create mapping for a specific table layout
python utils/region_selector.py test_results/your_table_image.png
```

### 2. Interactive Selection

- **Click and drag** to select player data regions
- **Press 't'** to test OCR on selected regions
- **Press 's'** to save regions to file
- **Press 'q'** to quit

### 3. Save Format

When saving, choose a descriptive name like:

- `standard_6v6` - Standard side-by-side format
- `stacked_teams` - Teams stacked vertically
- `detailed_table` - Tables with extra columns

## 📋 Format File Structure

Each `.json` file contains:

```json
{
  "image_path": "test_results/example.png",
  "regions": [
    {
      "start": [100, 200],
      "end": [300, 400],
      "name": "team1_players"
    },
    {
      "start": [350, 200],
      "end": [550, 400],
      "name": "team2_players"
    }
  ],
  "created_date": "2024-01-15",
  "description": "Standard 6v6 table format"
}
```

## 🧪 Testing Formats

```bash
# Test with specific format mapping
python test_local.py test_results/image.png --format-file formats/standard_6v6.json

# Interactive testing with format selection
python test_local.py --interactive --use-formats
```

## 💡 Tips for Good Mappings

1. **Select tight regions** around player data only
2. **Avoid headers/titles** in the selection
3. **Test thoroughly** with multiple similar images
4. **Create separate regions** for each team if side-by-side
5. **Include score columns** in the selection area

## 🔄 Usage in Bot

Once created, formats are automatically available in:

- Local testing scripts
- Discord bot OCR processing
- Batch processing tools

The bot will use the best matching format based on image characteristics.
