import os
import subprocess
import multiprocessing
from multiprocessing.pool import ThreadPool
import time
import re
import pandas as pd
import numpy as np
import itertools
import argparse
import pickle
import shlex

class application(object):
	def __init__(self, id):
		super().__init__()
		self.id = id
		self.friendly_score
		self.ram_usage
		self.swap_usage
		self.pids = []

	def set_friendly_score(self, fs):
		self.friendly_score = fs

	def set_ram_usage(self, ru):
		self.ram_usage = ru
	
	def set_swap_usage(self,su):
		self.swap_usage = su

	def set_pid(self, pid):
		self.pids.append(pid)


class scheduler(object):
	def __init__(self, interval, threshold, startid):
		super().__init__()
		self.app_status = pd.DataFrame(columns=["time","applicationid","pid","swap","ram",  'ws', 'hitratio', "status","suspended_time"])
		self.his_status = pd.DataFrame(columns=["time","applicationid","pid","swap","ram",  'ws', 'hitratio' , "status","suspended_time"])
		self.current_status = pd.DataFrame(columns=["time","applicationid","pid","swap","ram"])
		self.total_ram = 0
		self.cache_status = pd.DataFrame(columns=['applicationid', 'hitratio','ws','friendly_score']) 
		self.friendly_queue = []
		self.memory_usage_queue = None
		self.startid = startid
		self._interval = interval
		self._threshold = threshold
		
	def transUnit(self, s):
		if s=='':
			print('Warning: value is invalid')
		if s[-1] == 'g':
			return eval(s[:-1])
		elif s[-1] == 'm':
			return eval(s[:-1])/1024
		else:
			return eval(s)/1024/1024

	def transTime(self, s):
		timelist = s.split(":")
		time = int(timelist[0])*60*60+int(timelist[1])*60+int(timelist[2])
		return time

	def suspend(self, appid):
		assert appid in self.current_status["applicationid"].values
		pids = self.current_status[(appid == self.current_status["applicationid"]) & ('run'==self.app_status['status'])]["pid"].drop_duplicates()
		if not pids.empty:
			for pid in pids:
				subprocess.call(['sudo', 'kill', '-STOP', pid])
			self.app_status.loc[(appid==self.app_status["applicationid"]) & ('run'==self.app_status['status']) ,"status"] = "suspend"
			self.app_status.loc[(appid==self.app_status["applicationid"]) & ('suspend'==self.app_status['status']) ,"suspended_time"] = self.app_status["time"].iloc[0]
		else:
			print('Warning: '+appid+'is suspended')

	def resume(self, appid):
		assert appid in self.app_status["applicationid"].values
		if 'suspend' in self.app_status.loc[appid==self.app_status['applicationid'],'status'].values:
			pids = self.app_status[appid == self.app_status["applicationid"]]["pid"].drop_duplicates()
			for pid in pids:
				subprocess.call(['sudo', 'kill', '-CONT', pid])
			self.app_status.loc[appid==self.app_status["applicationid"], "status"] = "run"
			self.app_status.loc[appid==self.app_status["applicationid"],"suspended_time"] = np.nan
		else:
			print('Warning: '+appid+'is running')

	def set_memory_usage_queue(self):
		muq_df = self.current_status.groupby(["applicationid"], as_index=False).sum().sort_values(by=['ram'], ascending=False)
		self.memory_usage_queue = muq_df
		#self.memory_usage_queue = muq_df.applicationid.tolist()
		
	def set_cache_status(self):
		app = "application_1611060359896_00"
		start = self.startid + 1
		ds = {app+str(start):[0.5, 401],  
			app+str(start+1):[0.4, 302], 
			app+str(start+2):[0.6, 203],
			app+str(start+3):[0.8, 104],
			# 'application_1581715766481_0'+str(start+4):[0.5, 400],  
			# 'application_1581715766481_0'+str(start+5):[0.4, 300], 
			# 'application_1581715766481_0'+str(start+6):[0.6, 200],
			# 'application_1581715766481_0'+str(start+7):[0.8, 100]
			}
		apps = scd.app_status[scd.app_status["status"]!='finish'].applicationid.drop_duplicates().values
		scd.cache_status = pd.DataFrame(columns=['applicationid', 'hitratio','ws','friendly_score']) 
		for app in apps:
			if app in ds:
				scd.cache_status.loc[-1] = [app, ds[app][0], ds[app][1], ds[app][0]/ds[app][1]]
				scd.cache_status.index = scd.cache_status.index + 1
		#self.cache_status = self.app_status[self.app_status["status"].isin(['run','suspend'])][['applicationid', 'ws', 'hitratio']].groupby(["applicationid","hitratio"], as_index=False).sum()
		#self.cache_status['hitratio'] = self.cache_status.join(self.app_status[['applicationid','hitratio']].set_index('applicationid'),on='applicationid')['hitratio']
		#self.cache_status['friendly_score'] = self.cache_status['hitratio']/100 + 1/ self.cache_status['ws'] * 4

	def set_friendly_queue(self):
		if len(self.cache_status)==0:
			print('Warning: no cache detected')
		else:
			self.friendly_queue = self.cache_status.sort_values(by='friendly_score', ascending=False).loc[:,'applicationid'].tolist()

	def top_tracker(self):
		#pids = subprocess.check_output(['pidof',"/usr/lib/jvm/jdk1.8.0_181/bin/java"]).decode('utf-8')
		#pidstr = re.sub("\s+", " -p ", pids.strip())
		process = subprocess.Popen(['top','-b','-n','1'],
									stdout=subprocess.PIPE,
									stderr=subprocess.PIPE,
									universal_newlines=True)
		#print(process.stderr.readlines())
		return process.stdout.readlines()
	
	def smem_tracker(self):
		command = ['sudo', 'smem']
		process = subprocess.Popen(command, 
									stdout=subprocess.PIPE, 
									stderr=subprocess.PIPE, 
									universal_newlines=True)
		return process.stdout.readlines()
		
	def perf_call(self, pids):
		pidstr = ''.join(pid+',' for pid in pids)
		command =  "sudo perf stat -x ',' -e cache-references,cache-misses,node-load-misses,node-loads -p " + pidstr +  " -- sleep %d"%(self._interval-1)
		p = subprocess.Popen(shlex.split(command), 
										stdout=subprocess.PIPE, 
										stderr=subprocess.PIPE, 
										universal_newlines=True)
		out, err = p.communicate()
		return (out, err)

	def perf_tracker(self):
		pool = ThreadPool(multiprocessing.cpu_count())
		results = {}
		appids = self.app_status[self.app_status['status']=='run'].applicationid.values
		for appid in appids:
			pids = self.app_status.loc[self.app_status['applicationid']==appid,'pid'].values
			results[appid] = (pool.apply_async(self.perf_call, args=(pids,)))
		pool.close()
		pool.join()
		return results

	def get_tracker_log(self):
		import datetime
		start = datetime.datetime.now()
		perf_logs = self.perf_tracker()
		perf = datetime.datetime.now()
		smem_logs = self.smem_tracker()
		smem = datetime.datetime.now()
		print("perf duration is:"+str(perf-start),"smem duration is:"+str(smem-perf) )
		return (perf_logs, smem_logs)

	def log_parser(self):
		"""extract information from a log file
		
		Arguments:
			trackerfile {[string]} -- [absolute pass of the log]
		"""
		self.current_status = pd.DataFrame(columns=["time","applicationid","pid","swap","ram"])
		top_logs = self.top_tracker()
		# parse top
		if len(top_logs) == 0:
			print('Warning: no applications running')
			return
		time = top_logs[0][6:14]
		self.total_ram = eval(top_logs[3].split()[3])/1024/1024
		self.free_ram = eval(top_logs[3].split()[5])/1024/1024
		for l in top_logs[7:]:
			if "/usr/lib/jvm/jdk1.8.0_181/bin/java -server" not in l or "/bin/bash -c" in l:
				continue
			words = l.split()
			pid = words[0]
			swap = self.transUnit(words[1])
			ram = self.transUnit(words[2])
			appid = words[6][71:101]
			self.current_status.loc[-1] = [time, appid, pid, swap, ram]
			self.current_status.index = self.current_status.index + 1
		# update app_status	
		current_pids = self.current_status['pid'].drop_duplicates()
		for pid in current_pids:
			if pid in self.app_status['pid'].values:
				for pid in self.current_status[self.current_status['pid']==pid]['pid']:
					self.app_status.loc[pid==self.app_status['pid'], 'ram'] = self.current_status.loc[pid==self.current_status['pid'], 'ram'].values
					self.app_status.loc[pid==self.app_status['pid'], 'swap'] = self.current_status.loc[pid==self.current_status['pid'], 'swap'].values
			else:
				if self.current_status[self.current_status['pid']==pid]['applicationid'].iloc[0] in self.app_status['applicationid'].drop_duplicates().values:
					self.app_status.loc[self.app_status['pid']==pid]['status'] = 'abandon'
				self.app_status = self.app_status.append(self.current_status[pid==self.current_status['pid'].values], sort=False, ignore_index=True)
				self.app_status.loc[pid==self.app_status['pid'], 'status'] = 'run'
		run_pids = self.app_status.loc[self.app_status['status'].isin(['run','suspend']),'pid'].drop_duplicates()
		for pid in run_pids:
			if pid not in current_pids.values:
				if 'suspend' in self.app_status.loc[ self.app_status['pid']==pid,'status'].values:
					self.app_status.loc[self.app_status['pid']==pid, 'status'] = 'abandon'
					print("Warning: suspended process killed")
				elif 'run' in self.app_status.loc[ self.app_status['pid']==pid,'status'].values:
					self.app_status.loc[ self.app_status['pid']==pid,'status'] = 'finish'
				else:
					print("Warning: Unknown status process killed")
		self.app_status.time = time
		

		# perf_logs, smem_logs = self.get_tracker_log()
		# #parse smem
		# new_lines = []
		# for line in smem_logs:
		# 	words = line.split()
		# 	if '/usr/lib/jvm/jdk1.8.0_181' in words[2]:
		# 		new_lines.append(words[:3]+words[-4:])
		# smem_df = pd.DataFrame(new_lines[1:], columns=['pid','user','command','paging','uss','pss','rss'])
		# smem_df.loc[:, 'uss'] = smem_df['uss'].apply(self.transUnit)
		# smem_df.loc[:, 'rss'] = smem_df['rss'].apply(self.transUnit)
		# smem_df.loc[:, 'paging'] = smem_df['paging'].apply(self.transUnit)
		# smem_df= smem_df[smem_df['pid'].isin(self.app_status['pid'])][['pid','uss','rss','paging']].reset_index().drop(['index'], axis=1)

		# # update ws
		# joined = self.app_status.join(smem_df.set_index("pid"), on='pid')
		# self.app_status["ws"] = joined["uss"] 
		# self.app_status["ram"] = joined["rss"]
		# self.app_status['swap'] = joined["paging"]
		# # parse perf and update cache hitratio
		# for appid in perf_logs:
		# 	out, err = perf_logs[appid].get()
		# 	#print("out: {} err: {}".format(out, err))
		# 	cr, cm, nm, nr = err.split("\n")[:4]
		# 	if '<not counted>' not in cm:
		# 		print(cm)
		# 		cache_hitratio = 100 - np.float(cm.split(",")[5])
		# 		#node_hitratio = 100 - float( nm.split(",")[0]) / float(nr.split(",")[0] )
		# 		self.app_status.loc[(self.app_status['applicationid']==appid)&(self.app_status["status"]!='finish'), "hitratio"] = cache_hitratio
		# 		#scd.app_status[ scd.app_status['applicationid']==appid]['node_hitratio'] = node_hitratio


	def scheduling(self):
		while True:
			self.log_parser()
			self.set_memory_usage_queue()
			#self.set_cache_status()
			self.set_friendly_queue()
			if (self.app_status['status']=='finish').all() and not self.app_status.empty:
				print("Info: End of Game")
				break
			if len(self.friendly_queue)==0:
				print('Info: No application running')
				continue
			#elif len(self.friendly_queue)==1:
			#	if (self.app_status.loc[self.app_status['applicationid']==self.friendly_queue[0], 'status'] == 'suspend').all():
			#		self.resume(self.friendly_queue[0])
			#	continue
			friendly_pool = self.friendly_queue[:(len(self.friendly_queue)+1)//2]
			unfriendly_pool = self.friendly_queue[(len(self.friendly_queue)+1)//2:]
			friendly_app = self.friendly_queue[0]
			if (self.app_status[self.app_status['applicationid']==friendly_app]['status']=='suspend').all():
				self.resume(friendly_app)
				continue
			total_memory_used = self.memory_usage_queue['ram'].sum()
			friendly_memory = self.memory_usage_queue.loc[self.memory_usage_queue['applicationid'].isin(friendly_pool),'ram'].sum()
			unfriendly_memory = self.memory_usage_queue.loc[self.memory_usage_queue['applicationid'].isin(unfriendly_pool),'ram'].sum()
			swapped_friendly = self.memory_usage_queue.loc[self.memory_usage_queue['applicationid']==friendly_app, 'swap'].values[0]
			if self.free_ram <= self.total_ram * 0.02 and swapped_friendly>0:
				if (friendly_memory - unfriendly_memory)/total_memory_used < self._threshold or unfriendly_memory > friendly_memory:
					print("Debug: START SUSPEND")
					freed_ram = 0
					cadidates = self.memory_usage_queue.loc[self.memory_usage_queue['applicationid'].isin(self.app_status[self.app_status['status']!='suspend']['applicationid'].values),'applicationid']
					apps_to_suspend = self.memory_usage_queue[self.memory_usage_queue['applicationid'].isin(set(scd.friendly_queue[1:]).intersection(cadidates))].join(self.cache_status.set_index('applicationid'), on='applicationid')
					while freed_ram < swapped_friendly and len(apps_to_suspend)>0: 
						if len(set(apps_to_suspend).intersection(set(unfriendly_pool)))==0:
							suspended_app = apps_to_suspend.sort_values(by='ram',ascending=False)['applicationid'].iloc[0]
						else:
							suspended_app = apps_to_suspend.sort_values(by='friendly_score',ascending=True)['applicationid'].iloc[0]
						self.suspend(suspended_app)
						apps_to_suspend = apps_to_suspend[ apps_to_suspend['applicationid']!=suspended_app]
						freed_ram += self.memory_usage_queue.loc[self.memory_usage_queue['applicationid']==suspended_app, 'ram'].values[0]

			if (friendly_memory - unfriendly_memory)/total_memory_used > (self._threshold + 0.1) or self.free_ram > self.total_ram * 0.02:
				suspended_apps = self.app_status[self.app_status['status']=='suspend']
				if not suspended_apps.empty:
					if (suspended_apps['applicationid'].isin(unfriendly_pool)).all():
						#suspended_apps = suspended_apps[suspended_apps['applicationid'].isin(unfriendly_pool)]
						resumed_app = suspended_apps.groupby(["suspended_time"], as_index=False).min().iloc[0].applicationid
					elif (suspended_apps['applicationid'].isin(friendly_pool)).any():
						suspended_apps = suspended_apps[suspended_apps['applicationid'].isin(friendly_pool)]
						suspended_apps = self.cache_status[self.cache_status['applicationid'].isin(suspended_apps.applicationid.values)]
						resumed_app = suspended_apps.sort_values(by='friendly_score', ascending=False).applicationid.loc[0]
					else:
						print('Warning: no suspended application')
					self.resume(resumed_app)

			self.his_status = self.his_status.append(self.app_status, sort=False, ignore_index=True)
			print("current: \n", self.current_status)
			print("tracker: \n", self.app_status)
			print("history: \n", self.his_status)
			time.sleep(scd._interval)
	
	def get_app_history(self, appid):
		return self.his_status[(self.his_status['applicationid']==appid) & (self.his_status['status']!='finish')]

	def monitor(self, name=None):
		while True:
			self.log_parser()			
			if (self.app_status['status']=='finish').all() and not self.app_status.empty:
				print("Info: End of Game")
				break
			self.his_status = self.his_status.append(self.app_status, sort=False, ignore_index=True)		
			#time.sleep(3)
		if name!=None:
			with open(name, 'wb') as his:
				pickle.dump(self.his_status, his)

#if __name__ == "__main__":

parser = argparse.ArgumentParser()
parser.add_argument("--startid", '-id', type=int, default=None)
parser.add_argument("--name", '-n', type=str, default=None)
parser.add_argument('--interval', '-i', type=int, default=10)
parser.add_argument('--threshold', '-t', type=float, default=0.8)
args = parser.parse_args()

scd = scheduler(args.interval, args.threshold, args.startid)
#scd.monitor()

# for i in range(10):
# 	#scd.monitor(args.name)
# 	#scd.scheduling()
# 	scd.log_parser()
# 	scd.set_memory_usage_queue()
# 	scd.set_cache_status()
# 	scd.set_friendly_queue()

# 	scd.his_status = scd.his_status.append(scd.app_status, sort=False, ignore_index=True)
#time.sleep(5)


while True:
	scd.log_parser()
	scd.set_memory_usage_queue()
	scd.set_cache_status()
	scd.set_friendly_queue()
	if (scd.app_status['status']=='finish').all() and not scd.app_status.empty:
		print("Info: End of Game")
		break
	if len(scd.friendly_queue)==0:
		print('Info: No application running')
		continue
	# elif len(scd.friendly_queue)==1:
	# 	if (scd.app_status.loc[scd.app_status['applicationid']==scd.friendly_queue[0], 'status'] == 'suspend').all():
	# 		scd.resume(scd.friendly_queue[0])
	# 	continue
	friendly_pool = scd.friendly_queue[:(len(scd.friendly_queue)+1)//2]
	unfriendly_pool = scd.friendly_queue[(len(scd.friendly_queue)+1)//2:]
	friendly_app = scd.friendly_queue[0]
	if (scd.app_status[scd.app_status['applicationid']==friendly_app]['status']=='suspend').all():
		scd.resume(friendly_app)
	else:
		total_memory_used = scd.memory_usage_queue['ram'].sum()
		friendly_memory = scd.memory_usage_queue.loc[scd.memory_usage_queue['applicationid'].isin(friendly_pool),'ram'].sum()
		unfriendly_memory = scd.memory_usage_queue.loc[scd.memory_usage_queue['applicationid'].isin(unfriendly_pool),'ram'].sum()
		swapped_friendly = scd.memory_usage_queue.loc[scd.memory_usage_queue['applicationid']==friendly_app, 'swap'].values[0]
		if scd.free_ram <= scd.total_ram * 0.02 and swapped_friendly>0:
			if (friendly_memory - unfriendly_memory)/total_memory_used < scd._threshold or unfriendly_memory > friendly_memory:
				print("Debug: START SUSPEND")
				freed_ram = 0
				cadidates = scd.memory_usage_queue.loc[scd.memory_usage_queue['applicationid'].isin(scd.app_status[scd.app_status['status']!='suspend']['applicationid'].values),'applicationid']
				apps_to_suspend = scd.memory_usage_queue[scd.memory_usage_queue['applicationid'].isin(set(scd.friendly_queue[1:]).intersection(cadidates))].join(scd.cache_status.set_index('applicationid'), on='applicationid')
				while freed_ram < swapped_friendly and len(apps_to_suspend)>0: 
					if apps_to_suspend.applicationid.isin(unfriendly_pool).all():
						suspended_app = apps_to_suspend.sort_values(by='ram',ascending=False)['applicationid'].iloc[0]
					else:
						suspended_app = apps_to_suspend.sort_values(by='friendly_score',ascending=True)['applicationid'].iloc[0]
					scd.suspend(suspended_app)
					apps_to_suspend = apps_to_suspend[ apps_to_suspend['applicationid']!=suspended_app]
					freed_ram += scd.memory_usage_queue.loc[scd.memory_usage_queue['applicationid']==suspended_app, 'ram'].values[0]

		if (friendly_memory - unfriendly_memory)/total_memory_used > (scd._threshold + 0.1) or scd.free_ram > scd.total_ram * 0.02:
			suspended_apps = scd.app_status[scd.app_status['status']=='suspend']
			if not suspended_apps.empty:
				if (suspended_apps['applicationid'].isin(unfriendly_pool)).all():
					suspended_apps = suspended_apps[suspended_apps['applicationid'].isin(unfriendly_pool)]
					resumed_app = suspended_apps.groupby(["suspended_time"], as_index=False).min().iloc[0].applicationid
				elif (suspended_apps['applicationid'].isin(friendly_pool)).any():
					suspended_apps = suspended_apps[suspended_apps['applicationid'].isin(friendly_pool)]
					suspended_apps = scd.cache_status[scd.cache_status['applicationid'].isin(suspended_apps.applicationid.values)]
					resumed_app = suspended_apps.sort_values(by='friendly_score', ascending=False).applicationid.iloc[0]
				else:
					print('Warning: no suspended application')
				scd.resume(resumed_app)

	scd.his_status = scd.his_status.append(scd.app_status, sort=False, ignore_index=True)
	print("current: \n", scd.current_status)
	print("tracker: \n", scd.app_status)
	print("history: \n", scd.his_status)
	time.sleep(scd._interval)
if args.name:
	with open(args.name, 'wb') as his:
		pickle.dump(scd.his_status, his)


def plot_fs(his_status=None, name=None):
	import pickle
	import matplotlib

	matplotlib.use('Agg')

	import matplotlib.pyplot as plt

	if his_status is None:
		with open(name,'rb') as his:
			his_status = pickle.load(his)

	colors = "bgrcmyk"
	fig, (ax1,ax2,ax3) = plt.subplots(3)
	apps = his_status.applicationid.drop_duplicates().sort_values().tolist()
	his_status['working'] = his_status['status']=='run'
	his_status = his_status[his_status['status']!='finish']
	def transTime(s):
		timelist = s.split(":")
		time = int(timelist[0])*60*60+int(timelist[1])*60+int(timelist[2])
		return time
	his_status.loc[:, 'time'] = his_status['time'].apply(transTime)
	his_status.loc[:, 'time'] -= his_status['time'].iloc[0]
	for appid in range(len(apps)):
		df  = his_status[his_status["applicationid"]==apps[appid]]
		appDF = df.groupby(["time","hitratio"],as_index=False).sum()
		appDF['fs1'] = appDF['hitratio']/appDF["ws"]
		appDF['fs2'] = appDF['hitratio']/100 + 1/appDF["ws"]
		appDF['fs3'] = appDF['hitratio']/200 +1/appDF["ws"] * 4
		ax1.plot(appDF["hitratio"], color=colors[appid], label=apps[appid][-4:])
		ax2.plot(appDF["ws"], color=colors[appid], label=apps[appid][-4:])
		ax3.plot(appDF["fs3"], color=colors[appid], label=apps[appid][-4:])
	ax1.legend(loc='upper center',ncol=4,fontsize='medium', bbox_to_anchor=(0.5, 1.3))
	ax1.set(ylabel="hitratio")
	ax2.set(ylabel="working_set_size")
	ax3.set(ylabel="friendly_score")
	plt.savefig('/home/labuser/Dropbox/projects/plot_fs_'+ name +'.png')

def plot_memory_usage(his_status=None, name=None):
	import pickle
	import matplotlib

	matplotlib.use('Agg')

	import matplotlib.pyplot as plt
	
	if his_status is None:
		with open(name,'rb') as his:
			his_status = pickle.load(his)

	colors = "bgrcmyk"
	fig, (ax1,ax2,ax3) = plt.subplots(3)
	fig.suptitle('RAM and SWAP Usage For Friendly (21, 1, 6, 19)')
	ax1.set(ylabel="RAM(GB)")
	ax2.set(ylabel="SWAP(GB)")
	ax3.set(ylabel="Status")
	plt.xlabel("time(s)")
	apps = his_status.applicationid.drop_duplicates().sort_values().tolist()
	his_status['working'] = his_status['status']=='run'
	his_status = his_status[his_status['status']!='finish']
	def transTime(s):
		timelist = s.split(":")
		time = int(timelist[0])*60*60+int(timelist[1])*60+int(timelist[2])
		return time
	his_status.loc[:, 'time'] = his_status['time'].apply(transTime)
	his_status.loc[:, 'time'] -= his_status['time'].iloc[0]
	for appid in range(len(apps)):
		df  = his_status[his_status["applicationid"]==apps[appid]]
		appDF = df.groupby(["time"],as_index=False).sum()
		ax1.plot(appDF["ram"], color=colors[appid], label=apps[appid][-4:])
		ax2.plot(appDF["swap"], color=colors[appid], label=apps[appid][-4:])
		x = list(range(appDF['time'].iloc[-1]+1))
		y = [] 
		for i in appDF.index:
			if i==0:
				y = y + [ [1]*appDF['time'].iloc[i] ]
			elif appDF["working"].iloc[i] == 5:
				y = y + [ [1]*(appDF['time'].iloc[i]-appDF['time'].iloc[i-1]) ]
			else:
				y = y + [ [-1]*(appDF['time'].iloc[i]-appDF['time'].iloc[i-1])]
		y = sum(y, [])
		ax3.plot(x[:-1], y, color=colors[appid], label=apps[appid][-4:])
		ax1.get_xaxis().set_visible(False)
		ax2.get_xaxis().set_visible(False)
		ax1.set_visible(True)
		ax2.set_visible(True)
		ax3.set_ylim(-2, 2)
	ax1.legend(loc='upper center',ncol=4,fontsize='medium', bbox_to_anchor=(0.5, 1.2))
	plt.savefig('/home/labuser/Dropbox/projects/plot_memory_'+name+'.png')


