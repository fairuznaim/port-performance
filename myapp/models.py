from django.db import models

class AISData(models.Model):
    id = models.AutoField(primary_key=True)
    mmsi = models.IntegerField()
    received_at = models.DateTimeField()
    station_id = models.SmallIntegerField()
    msg_id = models.IntegerField()

    turn = models.FloatField(null=True, blank=True)
    speed = models.FloatField(null=True, blank=True)
    lat = models.FloatField()
    lon = models.FloatField()
    course = models.FloatField(null=True, blank=True)
    heading = models.FloatField(null=True, blank=True)

    imo = models.IntegerField(null=True, blank=True)
    callsign = models.CharField(max_length=50, null=True, blank=True)
    shipname = models.TextField(null=True, blank=True)
    shiptype = models.SmallIntegerField(null=True, blank=True)

    to_port = models.IntegerField(null=True, blank=True)
    to_bow = models.IntegerField(null=True, blank=True)
    to_stern = models.IntegerField(null=True, blank=True)
    to_starboard = models.IntegerField(null=True, blank=True)

    destination = models.TextField(null=True, blank=True)
    draught = models.FloatField(null=True, blank=True)
    status = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'ais_vessel_combo'  
        managed = False                
        default_permissions = ()      
        auto_created = False

    def __str__(self):
        return f"{self.mmsi} - {self.received_at}"

class AISVesselFiltered(models.Model):
    mmsi = models.BigIntegerField()
    received_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=[
    ('Arrival', 'Arrival'),
    ('Postponed', 'Postponed'),
    ('Anchoring', 'Anchoring'),
    ('Approaching', 'Approaching'),
    ('Maneuvering', 'Maneuvering'),
    ('Berthing', 'Berthing'),
    ])
    turn = models.FloatField(null=True)
    speed = models.FloatField(null=True)
    lat = models.FloatField()
    lon = models.FloatField()
    course = models.FloatField(null=True)
    heading = models.FloatField(null=True)
    imo = models.BigIntegerField()
    callsign = models.CharField(max_length=50)
    shipname = models.CharField(max_length=100)
    shiptype = models.IntegerField(null=True)
    to_port = models.FloatField(null=True)
    to_bow = models.FloatField(null=True)
    to_stern = models.FloatField(null=True)
    to_starboard = models.FloatField(null=True)
    draught = models.FloatField(null=True)
    destination = models.CharField(max_length=100, null=True)
   
    class Meta:
        db_table = 'ais_vessel_filtered'
        managed = False

    def __str__(self):
        return f"{self.shipname} ({self.mmsi})"
    
class ShipPhaseDuration(models.Model):
    mmsi = models.BigIntegerField()
    phase = models.CharField(max_length=32)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    duration_minutes = models.FloatField()

    class Meta:
        db_table = 'ship_phase_duration'  # ❗ PostgreSQL table name
        verbose_name = 'Ship Phase Duration'
        verbose_name_plural = 'Ship Phase Durations'

    def __str__(self):
        return f"{self.mmsi} | {self.phase} | {self.duration_minutes:.1f} min"