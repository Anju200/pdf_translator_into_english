# pdf_translator_into_english(With Image Preservation)

This project is a web application built with [Panel](https://panel.holoviz.org/) that allows you to:

- Upload a PDF in any language (max 50 MB)
- Extract all text and images from the PDF
- Translate the text to English using Google Gemini (Generative AI)
- Download a new PDF with the translated text and all original images preserved

## Features

- **Image Extraction:** Supports most common PDF image encodings, including ASCII85, FlateDecode, JPEG, JPEG2000, and PNG.
- **Text Translation:** Uses Google Gemini API for high-quality translation.
- **User Interface:** Simple drag-and-drop PDF upload, translation button, and download link for the translated PDF.
- **Cross-platform:** Works on Windows, Linux, and macOS.

## Requirements

- Python 3.8+
- A Google Gemini API key

## Installation

1. **Clone the repository:**

    ```sh
    git clone https://github.com/yourusername/your-repo-name.git
    cd your-repo-name
    ```

2. **Install dependencies:**

    ```sh
    pip install -r requirements.txt
    ```

3. **Set up your environment variables:**

    Create a `.env` file in the project root with your Gemini API key:

    ```
    GEMINI_API_KEY=your_gemini_api_key_here
    ```

    **Do NOT commit your `.env` file to GitHub.**

## Usage

Run the Panel app locally:

```sh
panel serve images3.py
```

Then open [http://localhost:5006/images3](http://localhost:5006/images3) in your browser.

## Deployment

You can deploy this app to [Render](https://render.com), [Railway](https://railway.app), or any cloud platform that supports Python and Panel.

- **Start command for deployment:**
    ```
    panel serve images3.py --address=0.0.0.0 --port=10000 --allow-websocket-origin=*
    ```
- **Set the `GEMINI_API_KEY` as an environment variable on your deployment platform.**

## File Structure

```
code.py           # Main Panel app
requirements.txt     # Python dependencies
.env                 # Your Gemini API key (not tracked by git)
README.md            # This file
```

## Notes

- The app creates temporary files for images during PDF generation and cleans them up automatically.
- Only images with supported formats (JPEG, PNG, JPEG2000) are included in the output PDF.
- If you encounter issues with certain PDFs, check the debug output for unsupported image filters.
