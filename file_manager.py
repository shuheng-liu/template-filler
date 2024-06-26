import os
import shutil
from fetcher import FlockFetcher, ProjectInfoFetcher, GenreFormer, StudentFetcher
from controller import Controller
from io_utils import safe_mkdir, extract_zip, zipdir, DocxInsertionWriter, TxtWriter
from global_utils import rreplace, get_time_str
import language_tool_python as langtool


class FileSystemManager:
    def __init__(self, zip_dir, extracted_dir, download_dir):
        safe_mkdir(zip_dir)
        safe_mkdir(extracted_dir)
        safe_mkdir(download_dir)

        self.ZIP_DIR = zip_dir
        self.EXTRACTED_DIR = extracted_dir
        self.DOWNLOAD_DIR = download_dir

    def save_uploaded(self, file, filename):
        uploaded_zip_path = os.path.join(self.ZIP_DIR, filename)
        file.save(uploaded_zip_path)
        return uploaded_zip_path

    @staticmethod
    def get_controller(project_root, post_processors=None):
        flock_fetcher = FlockFetcher(os.path.join(project_root, "flock"))
        program_fetcher = ProjectInfoFetcher(os.path.join(project_root, "program_info"))
        student_fetcher = StudentFetcher(root_dir=project_root, name_list_path="eval.csv", flock_fetcher=flock_fetcher)
        former = GenreFormer(os.path.join(project_root, "genre"))
        return Controller(genre_former=former, student_fetcher=student_fetcher, program_fetcher=program_fetcher,
                          post_processors=post_processors)

    @staticmethod
    def run_controller(project_root, controller, pre_para_id, lang=None, new_words=''):
        writer = DocxInsertionWriter(template_path=os.path.join(project_root, "style.docx"), pre_para_id=pre_para_id)
        output_dir = os.path.join(project_root, "output")
        if lang:
            controller.student_fetcher.set_cache()
            first_names = set(controller.student_fetcher.cache.first_name)
            last_names = set(controller.student_fetcher.cache.last_name)
            names = list(first_names.union(last_names))
            new_spellings = names + new_words.split()
            print('new spellings:', new_spellings)
            tool = langtool.LanguageTool(
                language=lang,
                remote_server=os.environ.get('LANGTOOL_SERVER', 'http://localhost:8010'),
                newSpellings=new_spellings,
            )
            gwriter = TxtWriter()
        else:
            tool, gwriter = None, None
        controller.write_to_disk(writer, output_dir=output_dir, language_tool=tool, grammar_writer=gwriter,
                                 match_policy='all')
        return output_dir

    def handle(self, file, filename, pre_para_id, check=True, post_processors=None, lang=None, new_words=''):
        # save uploaded zip, and get the dir
        filename = f"{get_time_str()}_{filename}"
        uploaded_zip_path = self.save_uploaded(file, filename)

        # extract zip to a new folder
        extracted_path = os.path.join(self.EXTRACTED_DIR, rreplace(filename, ".zip", ""))
        extract_zip(src=uploaded_zip_path, dest=extracted_path)
        os.remove(uploaded_zip_path)

        # instantiate a controller to handle the extracted folder
        controller = self.get_controller(extracted_path, post_processors=post_processors)
        if check:
            controller.check_texts(output="raise")

        # run the controller and generator docs, optionally gather error, info, debug
        output_dir = self.run_controller(extracted_path, controller, pre_para_id, lang=lang, new_words=new_words)

        # zip the docs folder and return download path
        download_path = os.path.join(self.DOWNLOAD_DIR, filename)
        zipdir(output_dir, download_path)
        shutil.rmtree(extracted_path)

        return filename
