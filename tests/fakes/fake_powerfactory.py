class FakePowerFactory:
    def __init__(self):
        self.objects = []
        self.objects_created_in_current_unit = []

    def find(self, class_name, external_id):
        return next((obj for obj in self.objects if obj["class_name"] == class_name and obj["external_id"] == external_id), None)

    def create(self, class_name, external_id):
        obj = {"class_name": class_name, "external_id": external_id}
        self.objects.append(obj)
        self.objects_created_in_current_unit.append(obj)
        return obj

    def set_attributes(self, obj, values):
        if values.get("technology") == "FAIL":
            raise RuntimeError("injected")
        obj.update(values)

    def delete(self, obj):
        if obj in self.objects:
            self.objects.remove(obj)
        if obj in self.objects_created_in_current_unit:
            self.objects_created_in_current_unit.remove(obj)

    def count(self, class_name, external_id):
        return sum(obj["class_name"] == class_name and obj["external_id"] == external_id for obj in self.objects)
