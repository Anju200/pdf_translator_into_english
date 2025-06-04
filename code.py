import panel as pn
import PyPDF2
from fpdf import FPDF
import google.generativeai as genai
import os
import io
from dotenv import load_dotenv, find_dotenv
from PIL import Image
import zlib
import base64
import tempfile

_ = load_dotenv(find_dotenv())
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
pn.extension()

file_input = pn.widgets.FileInput(accept='.pdf')
translate_button = pn.widgets.Button(name="Translate PDF to English", button_type="primary")
generate_pdf_button = pn.widgets.Button(name="Generate PDF", button_type="success", visible=False)
status_pane = pn.pane.Markdown("")
output_text = pn.widgets.TextAreaInput(name="Translated Text", height=300, width=500, value="", disabled=True)
pdf_download = pn.widgets.FileDownload(
    label="Download Translated PDF",
    filename="translated_output.pdf",
    embed=False,
    visible=False
)

uploaded_pdf_text = {"text": ""}
translated_text = {"text": ""}
extracted_images = []  # List of (page_number, image_bytes, image_ext)

def decode_flate_png(xobj_item, data=None):
    """Try to reconstruct a PNG from FlateDecode image stream."""
    try:
        width = xobj_item.get("/Width")
        height = xobj_item.get("/Height")
        bpc = xobj_item.get("/BitsPerComponent", 8)
        color_space = xobj_item.get("/ColorSpace")
        if data is None:
            data = xobj_item.get_data()
        # Only handle DeviceRGB and DeviceGray for now
        if color_space == "/DeviceRGB":
            mode = "RGB"
        elif color_space == "/DeviceGray":
            mode = "L"
        else:
            print(f"DEBUG: Unsupported color space for FlateDecode: {color_space}")
            return None, None
        img = Image.frombytes(mode, (width, height), data)
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        return img_byte_arr.getvalue(), "png"
    except Exception as e:
        print(f"DEBUG: FlateDecode PNG reconstruction failed: {e}")
        return None, None

def decode_ascii85(data):
    try:
        # PyPDF2 returns bytes, but ASCII85 is ASCII text, so decode to str first
        if isinstance(data, bytes):
            data = data.decode('utf-8', errors='ignore')
        return base64.a85decode(data, adobe=True)
    except Exception as e:
        print(f"DEBUG: ASCII85 decode failed: {e}")
        return None

def extract_text_from_pdf(file_bytes):
    global extracted_images
    extracted_images = []
    file_stream = io.BytesIO(file_bytes)
    reader = PyPDF2.PdfReader(file_stream)
    text = ""
    for i, page in enumerate(reader.pages):
        page_text = page.extract_text()
        images_found = False
        try:
            resources = page.get("/Resources")
            if resources is not None and hasattr(resources, "get_object"):
                resources = resources.get_object()
            if resources and "/XObject" in resources:
                xObject = resources["/XObject"]
                if hasattr(xObject, "get_object"):
                    xObject = xObject.get_object()
                for obj in xObject:
                    xobj_item = xObject[obj]
                    if hasattr(xobj_item, "get_object"):
                        xobj_item = xobj_item.get_object()
                    if xobj_item.get("/Subtype") == "/Image":
                        images_found = True
                        filter_type = xobj_item.get("/Filter")
                        filters = filter_type if isinstance(filter_type, list) else [filter_type]
                        data = xobj_item._data  # get raw stream data
                        # Handle ASCII85Decode (possibly combined with FlateDecode)
                        for f in filters:
                            if f == "/ASCII85Decode":
                                data = decode_ascii85(data)
                                if data is None:
                                    break
                            elif f == "/FlateDecode":
                                try:
                                    data = zlib.decompress(data)
                                except Exception as e:
                                    print(f"DEBUG: FlateDecode after ASCII85 failed: {e}")
                                    data = None
                                    break
                        ext = "bin"
                        img_bytes = None
                        if data:
                            if "/DCTDecode" in filters:
                                ext = "jpg"
                                img_bytes = data
                            elif "/JPXDecode" in filters:
                                ext = "jp2"
                                img_bytes = data
                            elif "/FlateDecode" in filters or "/ASCII85Decode" in filters:
                                # Try to reconstruct PNG from raw data
                                try:
                                    width = xobj_item.get("/Width")
                                    height = xobj_item.get("/Height")
                                    color_space = xobj_item.get("/ColorSpace")
                                    if color_space == "/DeviceRGB":
                                        mode = "RGB"
                                    elif color_space == "/DeviceGray":
                                        mode = "L"
                                    else:
                                        print(f"DEBUG: Unsupported color space for FlateDecode+ASCII85: {color_space}")
                                        continue
                                    img = Image.frombytes(mode, (width, height), data)
                                    img_byte_arr = io.BytesIO()
                                    img.save(img_byte_arr, format='PNG')
                                    img_bytes = img_byte_arr.getvalue()
                                    ext = "png"
                                except Exception as e:
                                    print(f"DEBUG: PNG reconstruction failed: {e}")
                        if img_bytes and ext != "bin":
                            extracted_images.append((i+1, img_bytes, ext))
                        else:
                            print(f"DEBUG: Skipping unsupported or failed image on page {i+1}")
        except Exception as e:
            print(f"DEBUG: Error checking images on page {i+1}: {e}")
        # Always add a header for each page
        text += f"\n--- Page {i+1} ---\n"
        if page_text and page_text.strip():
            text += page_text + "\n"
        else:
            text += "[No extractable text on this page]\n"
        if images_found:
            text += f"[Image present on page {i+1}]\n"
    return text

def split_text_by_pages(full_text, pages_per_chunk=10):
    # Split on page headers
    pages = full_text.split('\n--- Page ')
    if pages and not pages[0].strip():
        pages = pages[1:]
    chunks = []
    for i in range(0, len(pages), pages_per_chunk):
        chunk = '\n--- Page '.join(pages[i:i+pages_per_chunk])
        if not chunk.startswith('Page'):
            chunk = 'Page ' + chunk
        chunks.append(chunk)
    return chunks

def on_file_upload(event):
    if file_input.value:
        # Check file size
        if len(file_input.value) > 50 * 1024 * 1024:
            status_pane.object = "**PDF limit exceeded! Upload a file less than 50 MB.**"
            uploaded_pdf_text["text"] = ""
            output_text.value = ""
            generate_pdf_button.visible = False
            pdf_download.visible = False
            return
        status_pane.object = "**PDF uploaded!**"
        uploaded_pdf_text["text"] = extract_text_from_pdf(file_input.value)
        output_text.value = ""
        generate_pdf_button.visible = False
        pdf_download.visible = False
    else:
        status_pane.object = ""
        uploaded_pdf_text["text"] = ""
        output_text.value = ""
        generate_pdf_button.visible = False
        pdf_download.visible = False

def translate_pdf(event):
    if not uploaded_pdf_text["text"]:
        status_pane.object = "**Please upload a PDF file.**"
        return
    status_pane.object = "**Translation in process...**"
    full_text = uploaded_pdf_text["text"]
    page_chunks = split_text_by_pages(full_text, pages_per_chunk=10)
    translated = ""
    model = genai.GenerativeModel("models/gemini-2.0-flash")
    for idx, chunk in enumerate(page_chunks):
        prompt = (
            "Translate the following text to English. "
            "Keep the formatting as close as possible to the original. "
            "If you see '[Image present on page', just keep that note in the translation.\n\n"
            f"{chunk}"
        )
        response = model.generate_content(prompt)
        translated += response.text.strip() + "\n"
        status_pane.object = f"**Translating chunk {idx+1}/{len(page_chunks)}...**"
    output_text.value = translated
    translated_text["text"] = translated
    status_pane.object = "**Translation complete!**"
    generate_pdf_button.visible = True
    pdf_download.visible = False

def create_pdf(text):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", size=12)
    # Split text by page markers
    pages = text.split('\n--- Page ')
    if pages and not pages[0].strip():
        pages = pages[1:]
    # Organize images by page
    images_by_page = {}
    for page_num, img_bytes, ext in extracted_images:
        images_by_page.setdefault(page_num, []).append((img_bytes, ext))
    temp_img_paths = []  # Track temp files for cleanup
    for idx, page_content in enumerate(pages):
        pdf.add_page()
        lines = page_content.splitlines()
        y = 10
        for line in lines:
            if line.startswith("[Image present on page"):
                for img_idx, (img_bytes, ext) in enumerate(images_by_page.get(idx+1, [])):
                    try:
                        if ext in ("jpg", "jp2", "png"):
                            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp_img:
                                tmp_img.write(img_bytes)
                                tmp_img.flush()
                                img_path = tmp_img.name
                            temp_img_paths.append(img_path)
                            pdf.image(img_path, x=10, y=y, w=100)
                            try:
                                img = Image.open(img_path)
                                img_height = img.height * 100 / img.width
                            except Exception:
                                img_height = 60
                            y += img_height + 5
                        else:
                            print(f"DEBUG: Skipping unsupported image format: {ext}")
                            continue
                    except Exception as e:
                        print(f"DEBUG: Error inserting image on page {idx+1}: {e}")
            else:
                pdf.set_xy(10, y)
                pdf.multi_cell(0, 10, line)
                y = pdf.get_y()
    output = pdf.output(dest='S')
    # Now cleanup temp files
    for img_path in temp_img_paths:
        try:
            os.remove(img_path)
        except Exception as e:
            print(f"DEBUG: Error deleting temp image file {img_path}: {e}")
    if isinstance(output, str):
        pdf_bytes = output.encode('latin1')
    else:
        pdf_bytes = bytes(output)
    return pdf_bytes

def on_generate_pdf(event):
    text = translated_text["text"]
    if not text.strip():
        status_pane.object = "**No translated text to generate PDF.**"
        pdf_download.visible = False
        return
    try:
        pdf_bytes = create_pdf(text)
        pdf_download.file = io.BytesIO(pdf_bytes)
        pdf_download.embed = True
        pdf_download.visible = True
        status_pane.object = "**PDF generated! Click to download.**"
    except Exception as e:
        pdf_download.visible = False
        status_pane.object = f"**Error creating PDF:** {e}"

file_input.param.watch(on_file_upload, 'value')
translate_button.on_click(translate_pdf)
generate_pdf_button.on_click(on_generate_pdf)

dashboard = pn.Column(
    pn.pane.Markdown("## PDF Translator\nUpload a PDF (max 50 MB) in any language and get the English translation as text."),
    file_input,
    status_pane,
    translate_button,
    output_text,
    generate_pdf_button,
    pdf_download,
)

dashboard.servable()
