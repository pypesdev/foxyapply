export namespace app {
	
	export class BrowserStatus {
	    running: boolean;
	    applying: boolean;
	    headless: boolean;
	    pageCount: number;
	    downloaded: boolean;
	    version: string;
	
	    static createFrom(source: any = {}) {
	        return new BrowserStatus(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.running = source["running"];
	        this.applying = source["applying"];
	        this.headless = source["headless"];
	        this.pageCount = source["pageCount"];
	        this.downloaded = source["downloaded"];
	        this.version = source["version"];
	    }
	}

}

export namespace store {
	
	export class LinkedInProfile {
	    id: number;
	    email: string;
	    password: string;
	    phoneNumber: string;
	    positions: string[];
	    locations: string[];
	    remoteOnly: boolean;
	    profileUrl: string;
	    yearsExperience: number;
	    userCity: string;
	    userState: string;
	    zipCode: string;
	    desiredSalary: number;
	    // Go type: time
	    createdAt: any;
	    // Go type: time
	    updatedAt: any;
	
	    static createFrom(source: any = {}) {
	        return new LinkedInProfile(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.id = source["id"];
	        this.email = source["email"];
	        this.password = source["password"];
	        this.phoneNumber = source["phoneNumber"];
	        this.positions = source["positions"];
	        this.locations = source["locations"];
	        this.remoteOnly = source["remoteOnly"];
	        this.profileUrl = source["profileUrl"];
	        this.yearsExperience = source["yearsExperience"];
	        this.userCity = source["userCity"];
	        this.userState = source["userState"];
	        this.zipCode = source["zipCode"];
	        this.desiredSalary = source["desiredSalary"];
	        this.createdAt = this.convertValues(source["createdAt"], null);
	        this.updatedAt = this.convertValues(source["updatedAt"], null);
	    }
	
		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}
	export class LinkedInProfileUpdate {
	    email: string;
	    password: string;
	    phoneNumber: string;
	    positions: string[];
	    locations: string[];
	    remoteOnly: boolean;
	    profileUrl: string;
	    yearsExperience: number;
	    userCity: string;
	    userState: string;
	
	    static createFrom(source: any = {}) {
	        return new LinkedInProfileUpdate(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.email = source["email"];
	        this.password = source["password"];
	        this.phoneNumber = source["phoneNumber"];
	        this.positions = source["positions"];
	        this.locations = source["locations"];
	        this.remoteOnly = source["remoteOnly"];
	        this.profileUrl = source["profileUrl"];
	        this.yearsExperience = source["yearsExperience"];
	        this.userCity = source["userCity"];
	        this.userState = source["userState"];
	    }
	}

}

