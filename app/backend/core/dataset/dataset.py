from Queue import Empty
from multiprocessing import Process, Value, Lock, Queue
import numpy as np
import csv, sys
import os
import h5py
import abc
import random
import json
import logging
from img2d import Img2DSerDe, Img2DColumn
from input import Schema, Input, Column, ComplexColumn, NumericColumn, VectorColumn, \
    CategoricalColumn


class Dataset(object):
    DATA_DIR_NAME = "data"
    FILE_NAME = "dataset.processed"
    SCHEMA_FILE = "schema.json"

    def __init__(self, schema, path):
        self._schema = schema
        self._path = path
        self._record_reader = RecordReader.factory("HDF5", path)

    def get_batch(self, batch_size=64):
        data = {}
        for column in self._schema.columns:
            data[column.name] = []
        records_count = self._record_reader.records_count
        i = 0
        while i < batch_size:
            inx = random.randrange(0, records_count)
            record = self._record_reader.read(inx)
            for column in self._schema.columns:
                value = column.process_on_read(record)
                if isinstance(value, np.ndarray) and value.ndim > 1:
                    value = value.ravel()
                data[column.name].append(value)
            i += 1
        return Data(data)

    @staticmethod
    def load(path):
        with open(os.path.join(path, Dataset.DATA_DIR_NAME, Dataset.SCHEMA_FILE)) as s:
            return Dataset(Schema.deserialize(json.load(s)), path)

    class Builder(object):
        def __init__(self, input, name, root_dir, parallelism_level=2, storage_type="HDF5"):
            if not isinstance(input, Input):
                raise TypeError("Must be set to an Input")
            self._input = input
            self._name = name
            self._root_dir = root_dir
            self._parallelism_level = parallelism_level
            self._storage_type = storage_type
            self._init(root_dir)

        def _init(self, root_dir):
            self._dataset_root_dir = os.path.join(root_dir, self._name + "-" + str(random.getrandbits(64)))
            self._dataset_data_dir = os.path.join(self._dataset_root_dir, Dataset.DATA_DIR_NAME)
            os.makedirs(self._dataset_data_dir)

        def build(self):
            self._validate_data_schema()
            csv_rows_chunks = np.array_split(self._process_csv_file(), self._parallelism_level)
            processor = []
            processed_records = Queue()
            for i in range(self._parallelism_level):
                p = RecordProcessor(self._input.schema.columns, processed_records, csv_rows_chunks[i])
                processor.append(p)
            for p in processor: p.start()
            record_write = RecordWriter.factory(self._storage_type, self._dataset_root_dir, self._input.schema.columns)
            completed_processor_num = 0
            record_idx = 0
            aggregated_metadata = []
            try:
                while completed_processor_num < self._parallelism_level:
                    record = processed_records.get(block=True, timeout=5)
                    if record is not RecordProcessor.Result:
                        record_write.write(record, record_idx)
                        record_idx += 1
                    else:
                        completed_processor_num += 1
                        aggregated_metadata.append(record.get)
            except Empty:
                logging.warning("Not all the threads completed as expected")
            record_write.close()

            self._merge_metadata(aggregated_metadata)
            self._serialize_data_schema()

            print "Records processed: " + str(record_idx)

            return Dataset(self._input.schema, self._dataset_root_dir)

        def _merge_metadata(self, dist_calc_metadata):
            """
            :param dist_calc_metadata: List of columns from different processes which contains metadata.
            :return:
            """
            metadata_by_column = {}
            for column in self._input.schema.columns:
                if column.metadata is not None:
                    metadata_by_column[column.name] = []

            for columns in dist_calc_metadata:
                for column in columns:
                    if column.metadata is not None:
                        metadata_by_column[column.name].append(column.metadata)

            for column in self._input.schema.columns:
                if column.metadata is not None:
                    for metadata in metadata_by_column[column.name]:
                        column.metadata.merge(metadata)

        def _process_csv_file(self):
            rows = []
            csv_file_path = self._input.schema.csv_file_path
            columns = self._input.schema.columns
            with open(csv_file_path, 'rb') as f:
                reader = csv.reader(f)
                try:
                    for row in reader:
                        # Trim row entries
                        row = [e.strip() for e in row]
                        rows.append(row)
                        for column in columns:
                            if (isinstance(column, NumericColumn) or isinstance(column, VectorColumn) or isinstance(
                                    column, CategoricalColumn)) and column.metadata is not None:
                                column.metadata.aggregate(row[column.columns_indexes[0]])
                except csv.Error as e:
                    sys.exit('Broken line: file %s, line %d: %s' % (csv_file_path, reader.line_num, e))

            return rows

        def _validate_data_schema(self):
            for column in self._input.schema.columns:
                if column.type is None:
                    raise TypeError("Please specify type for column: %s" % column.name)

        def _serialize_data_schema(self):
            with open(os.path.join(self._dataset_data_dir, Dataset.SCHEMA_FILE), 'w') as f:
                f.write(json.dumps(self._input.schema.serialize()))


class RecordWriter(object):
    def __init__(self, data_dir, columns):
        self._data_dir = data_dir
        self._columns = columns

    def factory(type, data_dir, columns):
        if type == "HDF5":
            return HDF5RecordWriter(data_dir, columns)
        raise TypeError("Unsupported Record Writer Type: " + type)

    factory = staticmethod(factory)

    def write(self, csv_row, idx):
        pass

    def close(self):
        pass


class RecordReader(object):
    def __init__(self, data_dir):
        self._data_dir = data_dir

    def factory(type, data_dir):
        if type == "HDF5":
            return HDF5RecordReader(data_dir)
        raise TypeError("Unsupported Record Writer Type: " + type)

    factory = staticmethod(factory)

    def read(self, idx):
        pass

    def close(self):
        pass


class HDF5RecordReader(RecordReader):
    def __init__(self, data_dir):
        super(HDF5RecordReader, self).__init__(data_dir)
        self._data_file = h5py.File(os.path.join(data_dir, Dataset.DATA_DIR_NAME, Dataset.FILE_NAME), 'r')
        self._data = self._data_file['data']
        self._data_keys = self._data_file['data'].keys()

    @property
    def records_count(self):
        return len(self._data_keys)

    def read(self, idx):
        key = self._data_keys[idx]
        hdf5_record = self._data[key]
        record = {}
        from h5py import Group
        for key in hdf5_record:
            if isinstance(hdf5_record[key], Group):
                sub_group = hdf5_record[key]
                value = {}
                for sub_key in sub_group:
                    value[sub_key] = sub_group[sub_key].value
                record[key] = (value)
            else:
                record[key] = hdf5_record[key].value
        return record

    def close(self):
        self._data_file.close()


class HDF5RecordWriter(RecordWriter):
    def __init__(self, data_dir, columns):
        super(HDF5RecordWriter, self).__init__(data_dir, columns)
        self._file = h5py.File(os.path.join(self._data_dir, Dataset.DATA_DIR_NAME, Dataset.FILE_NAME), 'w')
        self._root_data = self._file.create_group('data')

    def write(self, record, idx):
        row_data = self._root_data.create_group('row_%08d' % idx)
        for col_name, value in record.iteritems():
            if isinstance(value, dict):
                sub_cal_name = row_data.create_group(col_name)
                for key in value:
                    # https://www.bountysource.com/issues/36647663-save-jpeg-images-in-h5py
                    if isinstance(value[key], str):
                        sub_cal_name[key] = np.void(value[key])
                    else:
                        sub_cal_name[key] = value[key]
            else:
                if isinstance(value, str):
                    row_data[col_name] = np.void(value)
                else:
                    row_data[col_name] = value

    def close(self):
        self._file.close()


class RecordProcessor(Process):
    def __init__(self, columns, result_queue, csv_rows):
        super(RecordProcessor, self).__init__()
        self._columns = columns
        self._result_queue = result_queue
        self._csv_rows = csv_rows

    class Result:
        def __init__(self, columns):
            self._columns = columns

        @property
        def get(self):
            return self._columns

    def run(self):
        for csv_row in self._csv_rows:
            processed_row = {}
            for column in self._columns:
                processed_row[column.name] = column.process_on_write(csv_row)
            self._result_queue.put(processed_row)
        # Signalize that processing is completed and send back columns with it's metadata
        self._result_queue.put(RecordProcessor.Result(self._columns))


class Data(object):
    def __init__(self, data):
        self._data = {}
        for key in data.keys():
            self._data[key] = np.array(data[key])

    def __getitem__(self, column_name):
        return self._data[column_name]


class Metadata(object):
    def __init__(self):
        print ""


if __name__ == '__main__':
    from img2d import Img2DColumn, Img2DReader, ImgResizeTransform
    from input import Schema, Input, ColumnSerDe, ColumnSerDe
    import os
    import glob

    #
    pathCSV = '../../../../data-test/dataset-image2d/simple4c_test/test-csv-v1.csv'
    if not os.path.isfile(pathCSV):
        raise Exception('Cant find file [%s]' % pathCSV)
    wdir = os.path.abspath(os.path.dirname(pathCSV))
    schema = Schema(pathCSV, header=True, separator='|')
    schema.print_data()
    input = Input(schema=schema)
    # dataset = Dataset()
    print ('----')
