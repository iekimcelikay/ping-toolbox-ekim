'''
NOTE TO COLLABORATORS: THIS IS ABSOLUTELY A WORK IN PROGRESS!!!!
Auditory Temporal pRF Experiment
- FIXATION COLOR CHANGE TASK REMOVAL 04/05/2026
- Another task will be implemented when decided.

Two classes:
    Presentation — owns all PsychoPy visual state (window, cross, drawing)
    Experiment   — owns all experiment logic (timing, trials, data logging)
Audio playback mechanics are placeholders — to be implemented.



TIMING:
ptb_reference = time of trigger 1 (used to measure inter-trigger intervals)
run_start_abs = (t=0 for run) time just after trigger 4 = actual run start that all trial/color-change times are added to.


rel_onset_ms (computed at prepare_trials) - the relative onset time of each tone within the
5-second trial window (e.g., tone every 200+146 ms = onsets at 0, 346, 692, ... ms)
'''
## TODOS:
# // [ ] Save to .csv function!!!
# // [ ] debug prints should be turned into logs
import pandas as pd
from psychopy import core, event, visual, logging
import os
import wave
import psychtoolbox as ptb
import numpy as np
# Audio imports today

from psychtoolbox import PsychPortAudio


# ======== WIP SECTION BECAUSE I DON'T WANT TO SWITCH FILES ===============

## Logging things
#  --------------
# BIDS formatted Event files:
# filename: 'events.tsv' -> I may need to add subject or session tag here
# f
###########################################################################
# 9 temporal conditions, 4 CFs, 25% null trials, 3 rep of each condition in each run, 4 runs

# ============ DEFAULT CONFIG ============
DEFAULT_CONFIG = {
	# Timing
	'trial_duration' : 5.0,
	'opening_blank' : 10.0,
	'closing_blank' : 10.0,
	'tr' : 1.6,


	# Display
	'screen_size' : [300, 300],
	'screen_num' : 0,
	'monitor' : 'testMonitor',
	'fullscr' : False,

	# Audio
	'sample_rate' : 48000,
	'num_harmonics' : 1,
	'harmonic_factor' : 0.7,
	'dbspl' : 70,
	'audio_device' : 'default',   # 'default' for testing; hw:X,0 for fMRI
	'latencyclass' : 1,           # 1 = shared low-latency; 3 = exclusive ALSA (fMRI)

	# RNG
	'seed' : None,

	# TEXT
    "BEGIN_TEXT"           : f"Welcome to the auditory pRF experiment",
    "BEGIN_INSTRUCTIONS"   : (f"During the experiment you will be presented with a fixation cross."
                                " Please keep your gazed fixed to it for the duration of the experiment. \n\n"
                                " You will be presented with a series of tones: "
                                " Your task is to pay attention to the color of fixation cross, at random times it will change. \n\n "
                                " If you see a color change, you must quickly press any key with the number 1, 2, 3, or 4. \n\n"
                                " If you are ready, press the space bar to begin the experiment."),
    "REST_HEADING"         : "Well done! Time to take a break.",
    "REST_TEXT"            : f"Please feel free to rest up to 2 min. You can move, or even step outside for a moment.\n\n "
                            "Once you are ready to continue, put the headphones on and press the spacebar.",

    "END_HEADING"          : "The end of the experiment.",
    "END_TEXT"             : "You can now relax. Thank you so much for your participation!\n\n",

}

# MODULE LEVEL FUNCTIONS

def _shuffle_no_adjacent_nulls(trials):

	rng = np.random.default_rng()
	# Step 1: separate actives and nulls
	actives = [t for t in trials if t[2] is not None] # 3
	nulls = [t for t in trials if t[2] is None] #

	n_nulls = len(nulls)
	# Step 2: Shuffle the active trials randomly
	rng.shuffle(actives)

	# Step 3: there are len(actives) + 1 gaps
	# Pick # of them at random, without replacement (so at most one null per gap)
	n_gaps = len(actives) + 1 #
	null_gap_indices = set(
		rng.choice(n_gaps, size=n_nulls, replace=False)) #  unique gap indices

	# Step 4: build the result by walking through active trials,
	# inserting a null whenever the current gap index was chosen
	null_iter = iter(nulls)
	result = []
	for i, active in enumerate(actives):
		if i in null_gap_indices: # gap i is BEFORE active trial i
			result.append(next(null_iter))
		result.append(active)

	if n_gaps - 1 in null_gap_indices: # trailing gap
		result.append(next(null_iter))

	return result

# =============================================================================
#  AUDIO FUNCTIONS
# =============================================================================
def find_audio_device(devname):
	devices = PsychPortAudio('GetDevices')
	for i in range(len(devices)):
		if devices[i]['DeviceName'] == devname:
			return devices[i]['DeviceIndex']
	available = [devices[i]['DeviceName'] for i in range(len(devices))]
	raise RuntimeError(f"Audio device '{devname}' not found. Available: {available}")

def start_audio_device(deviceid, fs=None, channels=2, latencyclass=3):
	pahandle = PsychPortAudio('Open', deviceid, [], latencyclass, fs, channels)
	return pahandle

def schedule_audio(pahandle, sound_array, when_abs):
	PsychPortAudio('Stop', pahandle, 0)
	PsychPortAudio('FillBuffer', pahandle, sound_array)
	# ('Start', pahandle, repetitions, when, waitForStart)
	actual_start = PsychPortAudio('Start', pahandle, 1, when_abs, 1)
	return actual_start



# =============================================================================
# PRESENTATION CLASS
# Owns all Psychopy visual state. Experiment delegates all drawing here.
# Never calls ptb.WaitSecs - timing is always Experiment's responsibility.
# =============================================================================


class Presentation:

	def __init__(self, config):
		'''
        Parameters
        ----------
        config : dict
            Merged experiment config. Display keys are read here.
        '''
		self.config = config
		self.win = None # Psychopy window
		self.cross = None # fixation cross ShapeStim
		self.frame_dur = None # measured frame duration in seconds

	def setup(self):
		'''
        Open the PsychoPy window, measure frame duration, create fixation cross.
        Must be called before any drawing method.
        '''

		self.win = visual.Window(
			self.config['screen_size'],
			screen = self.config['screen_num'],
			monitor = self.config['monitor'],
			color = (0, 0, 0),
			fullscr = self.config['fullscr'],
			units = 'pix',
			allowGUI = True,
		)

		# Measure actual frame duration - used by Experiment for PTB wait offsets
		self.frame_dur = 1.0 / self.win.getActualFrameRate(nIdentical=60, threshold=1)
		print(f"DEBUG: Measured frame duration: {self.frame_dur:.5f} s")

		# Fixation cross - created once, color updated every frame in polling loop
		self.cross = visual.ShapeStim(
			win 	  = self.win,
			vertices  = 'cross',
			units     = 'deg',
			size      = (0.5, 0.5), #visual degrees!!!
			lineColor = 'white',
			fillColor = 'white',
			lineWidth = 1.0,
		)

	def close(self):
		'''Close the window.'''
		if self.win is not None:
			self.win.close()



	def draw_blank(self):
		'''
		# //FIXME: SInce fixation color task is removed, this also needs to be
		# //FIXME: Used in the normal presentation/
        Draw a white fixation cross on a blank screen and flip.
        Used by Experiment._run_blank() for opening/closing blanks and ITIs.
        No waiting — Experiment handles the PTB wait after calling this.
        '''
		self.cross.fillColor = 'white'
		self.cross.lineColor = 'white'
		self.cross.draw()
		self.win.flip()

	def show_text(self, text, height=36):
		# //TODO: make this show_body_text and create a show_heading_text method similarly.
		'''
        Create, draw, and flip a text stimulus.
        Used for BEGIN screen, rest screen, and any instructional screens.

        Parameters
        ----------
        text : str
        height : int
            Font height in pixels.
        '''
		stim = visual.TextStim(
			self.win,
			text = text,
			font = 'Arial',
			pos = (0,0),
			color = (-1, -1, -1),
			units = 'pix',
			height = height,
		)
		stim.draw()
		self.win.flip()

# =============================================================================
# EXPERIMENT CLASS
# Owns all experiment logic -- timing, trial, sequencing, scheduling, data logging.
# Delegates all drawing to self.presentation.
# =============================================================================


class Experiment:

	def __init__(self, config=None, pahandle=None, sound_gen=None, base_trials=None):
		'''
        Parameters
		----------
		config : dict, optional
            Experiment configuration. Merged with DEFAULT_CONFIG —
            keys provided override defaults.
        '''

		# Merge config with defaults:
		# Self-study comment: This uses dictionary unpacking.
		# The steps are like this: It unpacks the DEFAULT_CONFIG values first,
		# Then goes for the second argument, which would be config (these are the configs we
		# supplement in the run script if we want to use something else then the defaults.)
		# However, we don't want to write all the keys all again every time. HOwever then those
		# would be None, and the dictionary unpacking would give error (you can't give None here).
		# So it supllements empty dictionary if we don't change configs.

		self.config = {**DEFAULT_CONFIG, **(config or {})}

		# Presentation layer - owns window, cross, frame_dur
		self.presentation = Presentation(self.config)

		# Audio hardware - placeholder # // NOTE: i'm not sure if i shouuld add the pahandle here.
		self.pa_handle = pahandle # PsychportAudio handle


		# Timing anchors - set in show_begin_screen() / show_rest_screen()
		self.ptb_reference = None # absolute PTB epoch at first trigger each run (run start)
		self.run_start_abs = None # absolute PTB epoch after 4th trigger
		self.trigger_times = None
		# Control
		self.run_experiment = False
		self.current_run = 0

		# RNG
		self.rng = np.random.default_rng(self.config['seed'])

		# Trial generation -
		self.sound_gen = sound_gen # SoundGen instance
		self.base_trials = base_trials # list of (tone_on_ms, isi_ms, freq_hz) -- one rep

		# Trial pool -- populated in prepare_trials()
		self.trial_pool = None

		# Data -- accumulated across runs
		self.behavioral_log = []

	def _make_text_screen(self, text, height=36):
		self.presentation.show_text(text, height=height)


	# ==========================================================================
	# SETUP & TEARDOWN
	# ==========================================================================

	def setup(self):
		self.presentation.setup()
		deviceid = find_audio_device(self.config['audio_device'])
		self.pa_handle = start_audio_device(
			deviceid,
			fs=self.config['sample_rate'],
			channels=2,
			latencyclass=self.config['latencyclass'],
		)


	def teardown(self):
		'''Close display and audio hardware, save data.'''
		if self.pa_handle is not None:
			PsychPortAudio('Close', self.pa_handle)
		self.presentation.close()
		core.quit()

	# =========================================================================
	# TRIAL PREPARATION
	# =========================================================================


	def prepare_trials(self):
		'''
		Compute relative onset times for each trial and shuffle with no
		adjacent nulls. Waveforms are generated on the fly and in _run_trial().
		Call once per run.

		Trial tuples are stored in self.trial_pool:
			(tone_on_ms, isi_ms, freq_hz, rel_onsets_ms)
		'''
		# //TODO
		# //[ ]: YOu need to add more constraints to null trials.


		cfg = self.config
		total_duration = cfg['trial_duration']
		run_trials = []

		for tone_on_ms, isi_ms, freq_hz in self.base_trials:

			if freq_hz is None:
				# Null trial -- no tones, no onsets
				run_trials.append((0, 0, None, []))
				continue

			# Compute relative onset times in ms without generating waveform
			tone_duration = tone_on_ms / 1000.000
			isi = isi_ms / 1000.0
			num_tones, _, _ = self.sound_gen.calculate_num_tones(
				tone_duration, isi, total_duration
				)
			rel_onsets_ms = [
				k * (tone_duration + isi) * 1000
				for k in range(num_tones)
			]
			run_trials.append((tone_on_ms, isi_ms, freq_hz, rel_onsets_ms))

		# Shuffle with no adjacent rules -- identified by freq_hz is None
		self.trial_pool = _shuffle_no_adjacent_nulls(run_trials)
		print(f"DEBUG: Trial pool prepared -- {len(self.trial_pool)} trials")

	# =========================================================================
	# SCREEN HELPERS
	# =========================================================================

	def _wait_for_triggers(self, label):

		trigger_times = []

		# Trigger 1 -- wait for the trigger, and record whenn it happens.
		key = event.waitKeys(keyList=['s'], clearEvents=False)
		print(f"DEBUG: keypress={key}")
		self.ptb_reference = ptb.GetSecs()
		trigger_times.append(self.ptb_reference)
		print(f"DEBUG: {label} -- Acquisition start (1/4 triggers): "
			f"{self.ptb_reference:.5f}")

		# Wait for 3 more triggers -- print inter-trigger intervals
		for i in range(2,5):
			key = event.waitKeys(keyList=['s'], clearEvents=False)
			print(f"DEBUG: keypress={key}")
			t = ptb.GetSecs()
			trigger_times.append(t)
			print(f"DEBUG: {label} -- Trigger ({i}/4): "
				f"{t - self.ptb_reference:.5f}")

		# Run starts after 4th trigger
		self.run_start_abs = ptb.GetSecs()
		self.trigger_times = trigger_times # stored for logging
		print(f"DEBUG: {label} -- Run start (4/4 triggers): "
			f"{self.run_start_abs - self.ptb_reference:.5f}")


	# =========================================================================
	# BEGIN SCREEN
	# =========================================================================

	def show_begin_screen(self):
		'''
		Show BEGIN screen and wait for scanner trigger (s) or quit (q).
		Sets self.ptb_reference on first trigger.
		Returns True if experiment should start, False if aborted.
		'''

		self._make_text_screen('BEGIN press space to begin press q to quit. When demoing dont forget to press s', height=72)


		key = event.waitKeys(keyList=['space', 'q'], clearEvents=True)
		print(f"DEBUG: show_begin_screen -- key pressed: {key}")
		if 'q' in key:
			self.teardown()
			return False

		# I want to print out to the terminal the key presses.
        # // [ ]: ADD A FUNCTION TO PRINT THE KEY PRESSES TO THE TERMINAL WINDOW
		self.run_experiment = True
		self._wait_for_triggers(label='Experiment')
		return True

	def show_rest_screen(self):
		'''
		Show rest screen between runs and wait for next scanner trigger.
		Resets self.run_start_abs for the upcoming run.
		Returns True if experiment should continue, False if aborted.
		'''
		self._make_text_screen(
			f'Run {self.current_run} complete. Rest.\nPress spacebar to continue.',
			height=36,
			)

		key = event.waitKeys(keyList=['space', 'q'], clearEvents=True)
		print(f"DEBUG: show_rest_screen -- key pressed: {key}")
		if 'q' in key:
			self.teardown()
			return False

		self._wait_for_triggers(label=f'Run {self.current_run + 1}')
		return True


	# =========================================================================
	# TRIAL HELPERS
	# =========================================================================

	def _build_timeline(self):

		cfg = self.config
		trial_onsets = []
		trial_offsets = []
		tone_onsets_rel = []

		t = cfg['opening_blank']
		for trial in self.trial_pool:
			trial_onsets.append(t)
			trial_offsets.append(t + cfg['trial_duration'])

			_, _, _, rel_onsets_ms = trial # 4-tuple
			for onset_ms in rel_onsets_ms:
				tone_onsets_rel.append(t + onset_ms / 1000.0)
		# // NOTE: YOU DON'T NEED ITI APPARENTLY.  REMOVE ITI
		# // [ ]: REMOVE ITI
			# ITI uniformly sampled from [1.0, 1.5 seconds]
			t += cfg['trial_duration'] + self.rng.uniform(1.0, 1.5)

		return trial_onsets, trial_offsets, tone_onsets_rel


	def _run_blank(self, end_time_abs):
		self.presentation.draw_blank()
		ptb.WaitSecs('UntilTime', end_time_abs - self.presentation.frame_dur)

	# =========================================================================
	# TRIAL EXECUTION
	# =========================================================================
	def _run_trial(self, trial, sequence, trial_start_abs, trial_start_rel, color_change_times):
		'''
		Execute a single 5-second trial. // FIXME: YOU NEED LONGER TRIALS
        // NOTE: If you don't have ITI you can't generate sounds on the go.
		Waveform must be pre-generated by the caller (during the ITI) and passed
		as `sequence`. This ensures generation cost never falls inside the
		WaitSecs → trial-boundary window.


		Parameters
		---------
		trial  : tuple
				(tone_on_ms, isi_ms, freq_hz, rel_onsets_ms)
		sequence : np.ndarray or None
				Pre-generated stereo audio array (2, n_samples). None for null trials.
		trial_start_abs : float
		trial_start_rel : float
		color_change_times: list of float

		Returns
		-------
		log : dict
		abs_onsets_ms : list of float
			Absolute tone onset times in ms relative to run start.
		'''

		cfg = self.config
		_, _, freq_hz, rel_onsets_ms = trial

		if sequence is not None:
			schedule_audio(self.pa_handle, sequence, trial_start_abs)

        # // FIXME: REMOVE THE TASK SECTION OF THIS CODE
		# Find color change within this trial window
		trial_changes = [
			c for c in color_change_times
			if trial_start_rel <= c < trial_start_rel + cfg['trial_duration']
		]
		# At most one color change per trial by construction (min_gap > trial_duration)
		change_onset_rel = trial_changes[0] if trial_changes else None
		change_onset_abs = (self.run_start_abs + change_onset_rel
							if change_onset_rel is not None else None)


		# Absolute tone onsets in ms relative to run start
		abs_onsets_ms = [trial_start_rel * 1000 + t for t in rel_onsets_ms]

		# Behavioral log
		log = {'hit': False, 'miss': False, 'false_alarm': False, 'rt': None}
		response_logged = False

		# --- POLLING LOOP -----------------------------------------------------
		trial_end_abs = trial_start_abs + cfg['trial_duration']

		while ptb.GetSecs() < trial_end_abs - self.presentation.frame_dur:

			t_now = ptb.GetSecs()

			self.presentation.draw_fixation(change_onset_abs, t_now)


			# Key presses
			keys = event.getKeys(keyList= ['1', '2', '3', '4', 'q'])
			event.clearEvents()

			if keys:
				print(f"DEBUG: key pressed ={keys} t_now={t_now:.4f}")

			if 'q' in keys:
				# //TODO: save whatever is accumulated
				# //TODO: write interrupted flag for current run
				self.teardown()

			response_logged = self._classify_response(
				keys, t_now, change_onset_abs, log, response_logged
				)

		# miss check
		if change_onset_abs is not None and not log['hit']:
			log['miss'] = True

		return log, abs_onsets_ms

	def _run_trial_loop(self, trial_onsets, color_change_times):
		'''
		Iterate over all trials in self.trial_pool, wait to each trial start,
		execute the trial, and collect per-trial logs.

		Parameters
		----------
		trial_onsets  :  list of float
			Trial start times in SECONDS relative to run start. (BIDS wants seconds)
		color_change_times  :  list of float
			Color change times in SECONDS relative to run start.

		Returns
		-------
		list of dict
			Per-trial behavioral log entries.

		'''

		run_log = []
		cfg = self.config

		for i, trial in enumerate(self.trial_pool):
			trial_start_rel = trial_onsets[i]
			trial_start_abs = self.run_start_abs + trial_start_rel

			# Generate during ITI — before WaitSecs so generation cost is outside
			# the timing-critical window before the trial boundary.
			tone_on_ms, isi_ms, freq_hz, rel_onsets_ms = trial

			if freq_hz is not None:
				sequence, _ = self.sound_gen.generate_sequence(
					freq = freq_hz,
					num_harmonics = cfg['num_harmonics'],
					tone_on_ms = tone_on_ms,
					isi_ms = isi_ms,
					harmonic_factor = cfg['harmonic_factor'],
					dbspl = cfg['dbspl'],
					total_duration = cfg['trial_duration'],
					)
			else:
				sequence = None

			# Wait precisely until trial start
			ptb.WaitSecs('UntilTime',
						trial_start_abs - self.presentation.frame_dur)
			print(f"DEBUG: trial start, run: {self.current_run+1}"
		 		f"trial {i+1}"
				f"freq {trial[2]}HZ")
			log, abs_onsets_ms = self._run_trial(
				trial, sequence, trial_start_abs, trial_start_rel, color_change_times
			)

			run_log.append({
				'run'			:self.current_run + 1,
				'trial_idx'		: i,
				'trial_onset_rel' : trial_start_rel,
				'run_start_abs'   : self.run_start_abs,
				'freq_hz'		: trial[2],
				'tone_on_ms'	: trial[0],
				'isi_ms' 		: trial[1],
				'abs_onsets_ms' : abs_onsets_ms,
				**log,
			})
            # // FIXME: RESPONSES NEEDS TO GO FOR NOW
			print(f"DEBUG: Run {self.current_run + 1} | "
                  f"Trial {i + 1}/{len(self.trial_pool)} | "
                  f"freq={trial[2]} Hz | "
                  f"hit={log['hit']} miss={log['miss']} fa={log['false_alarm']}")

		return run_log

	# =========================================================================
	# RUN
	# =========================================================================

	def run(self):
		'''
		Execute one run of the experiment.
		prepare_trials() and show_begin_screen() must be called before each run.

		Returns run_log -- list of per-trial dicts.
				- trial_onsets  :  list of trial start times (seconds from run start)
				- trial_offsets :  list of trial end times
				- tone_onsets_rel : flat list of every individual tone onset time across all trials
					-- seconds from run start --- used by the color change scheduler to avoid clashes
		'''
		assert self.trial_pool is not None, \
			"Call prepare_trials() before run()."
		assert self.run_start_abs is not None, \
			"Call show_begin_screen() before run()."

		cfg = self.config

		# STEP 1 --- BUILD TIMELINE ------------------------------------
		# full run timeline upfront before anything plays
		# Walks trhough trial_pool and assigns each trial an absolute start time relative to run_start_abs:
		# t = opening_blank (10 s)
		# trial 0 starts at t=10.0 s
		# trial 0 ends at   t=15.0 s
		# ITI ~ uniform(1.0, 1.5 s) # FIXME: ITI IS GOING TO BE REMOVED
		# trial 1 starts at t~16.2 s
		trial_onsets, trial_offsets, tone_onsets_rel = self._build_timeline()
		run_duration = trial_offsets[-1] + cfg['closing_blank']

        # // FIXME: REMOVE THE COLOR CHANGE SCHEDULE STEP
		# STEP 2 --- COLOR CHANGE SCHEDULE -------------------------------------------
		# places color changes at jittered positions (6-10 s apart) across the full run duration.
		# Each candidate ti e is checked against three constraints via _check_constraints():
		# 	1. must be >= 5 sc from the previous color change
		# 	2. must be >= 50 ms from any tone onset
		#   3. must be >= 500 ms from any trial boundary (start or end)
		# ALl color change times are relative to run start (same reference as trial_onsets).
		# generate for this run
		color_change_times = self._generate_color_change_schedule(
			run_duration, tone_onsets_rel, trial_onsets, trial_offsets
		)
		print(f"DEBUG: Run {self.current_run + 1} -- "
			f"{len(color_change_times)} color changes scheduled")

		# STEP 3 --- OPENING BLANK ---------------------------------------------------
		# 10 seconds of white fixation cross
		print(f"DEBUG: OPENING BLANK START")
		self._run_blank(self.run_start_abs + cfg['opening_blank'])
		print(f"OPENING BLANK FINISH")

		# STEP 4 --- TRIALS LOOP -----------------------------------------------------
		# for each trial:
		#   - waits (via ptb.WaitSecs('UntilTime',....)) until run_start_abs + trial_onset
		# Calls _run_trial()
		run_log = self._run_trial_loop(trial_onsets, color_change_times)

		# STEP 5 --- CLOSE SCREEN
		# closing blank -- 10 seconds
		self._run_blank(self.run_start_abs + run_duration)

		# STEP 6 --- SAVE AND RESET --------------------------------------------------
		# append run_log to self.behavioral_log, increments self.current_run, clears trial_pool
		self.behavioral_log.extend(run_log)
		self.current_run += 1
		self.trial_pool = None 				# Force prepare_trials() before next run

		return run_log


# ==============================================================================
# ENTRY POINT
# ==============================================================================

if __name__ == '__main__':

	## SETUP AND RUN LOOP
	# Everything starts here. It:
	# - defines stimuli parameter (9 temporal conditions x 36 frequencies = 324 active trials)
	# - computes null trial count: n_null = floor(324 x 0.33 / 0.67) ~= 159
	# - builds base_trials: a flat list of (tone_on_ms, isi_ms, freq_hz) tuples - 324 active + 159 nulls = 483 total.
	#	This list is the same every run -- it's the master stimulus set.
	# - Creates Experiment, calls setup() (opens window), then entrers the run loop.


    import sys
    sys.path.insert(0, '/home/ekim/auditory-pRF-subcortical')

    from auditory_prf.stimuli.soundgen import SoundGen
    from auditory_prf.utils.stimulus_utils import calc_cfs
    # ben bu asagidaki stimuli generation linelarinin exposed olmasindan hic memnun degilim
    # bence bu bi  fonksiyona donusturulmeli, ve bu temporal condition paramlar da
    # kendi configlerini almali.

    TONE_ON         = (54, 146, 146, 146, 200, 254, 800, 854, 5000) # 1st value of temporal condition pairs
    ISI             = (146, 54, 200, 854, 146, 54, 200, 146, 0) # 2nd value of temporal condition pairs
    NUM_FREQS       = 4 # Stimuli config
    MIN_FREQ        = 125 # Stimuli config
    MAX_FREQ        = 1900 # Stimuli config
    NUM_HARMONICS   = 5 # Stimuli config
    HARMONIC_FACTOR = 0.7 # Stimuli config
    DBSPL           = 70 # Stimuli config
    NULL_FRACTION   = 0.25 # Trial/Run design
    N_RUNS          = 4 # Trial/Run/Experiment design
    START_RUN       = 0 # SET TO RESUME FROM A SPECIFIC RUN (0-INDEXED)

    # Stimuli params
    desired_freqs       = calc_cfs((MIN_FREQ, MAX_FREQ, NUM_FREQS), species='human')
    temporal_conditions = list(zip(TONE_ON, ISI))

    stimuli = [
        (ton, isi, freq)
        for ton, isi in temporal_conditions
        for freq in desired_freqs
    ]
    # Null trials calc
    n_null      = int(np.floor(len(stimuli) * NULL_FRACTION / (1 - NULL_FRACTION)))
    base_trials = stimuli + [(0, 0, None)] * n_null

    config = {
        'seed'           : 42,
        'fullscr'        : False,
        'num_harmonics'  : NUM_HARMONICS,
        'harmonic_factor': HARMONIC_FACTOR,
        'dbspl'          : DBSPL,
    }
    sound_gen = SoundGen(config.get('sample_rate', 48000), tau=0.005)

    exp = Experiment(config, sound_gen=sound_gen, base_trials=base_trials)
    exp.setup()


    started = exp.show_begin_screen()
    if started:
        for run_idx in range(START_RUN, N_RUNS):
            if not exp.run_experiment:
                break

            exp.prepare_trials()
            run_log = exp.run()

            # //TODO: save run_log
            # //TODO: write completed flag for run_idx
            # //NOTE: If you keep the config as dict, then you can use json.dump(config, f)
            # to save configs as json files.

            if run_idx < N_RUNS - 1:
                if not exp.show_rest_screen():
                    break

    exp.teardown()